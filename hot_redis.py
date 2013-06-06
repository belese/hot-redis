
import operator
import uuid
import redis


client = redis.Redis()
lua_scripts = {}

def load_lua_scripts():
    with open("atoms.lua", "r") as f:
        for func in f.read().strip().split("function "):
            if not func:
                continue
            name, code = func.split("\n", 1)
            name = name.split("(")[0].strip()
            code = code.rsplit("end", 1)[0].strip()
            lua_scripts[name] = client.register_script(code)

load_lua_scripts()


class Base(object):

    def __init__(self, value=None, key=None):
        self.key = key or str(uuid.uuid4())
        if value:
            self.value = value

    def _dispatch(self, name):
        try:
            func = getattr(client, name)
        except AttributeError:
            pass
        else:
            return lambda *a, **k: func(self.key, *a, **k)
        try:
            func = lua_scripts[name]
        except KeyError:
            pass
        else:
            return lambda *a, **k: func(keys=[self.key], args=a, **k)
        try:
            func = getattr(self.value, name)
        except KeyError:
            pass
        else:
            return func
        raise AttributeError(name)

    def _to_value(self, value):
        if isinstance(value, self.__class__):
            return value.value
        return value

    def _op(self, op, value):
        return op(self.value, self._to_value(value))

    def _rop(self, op, value):
        right = self if isinstance(value, self.__class__) else self.value
        return op(value, right)

    def __getattr__(self, name):
        return self._dispatch(name)

    def __repr__(self):
        value = repr(self.value)
        return "%s(%s, '%s')" % (self.__class__.__name__, value, self.key)

    def __iter__(self):
        return iter(self.value)

    def __del__(self):
        self.delete()

    def __eq__(self, value):
        return self._op(operator.eq, value)

    def __lt__(self, value):
        return self._op(operator.lt, value)

    def __le__(self, value):
        return self._op(operator.le, value)

    def __gt__(self, value):
        return self._op(operator.gt, value)

    def __ge__(self, value):
        return self._op(operator.ge, value)


class Commutative(Base):

    def __add__(self, value):
        return self._op(operator.add, value)

    def __radd__(self, value):
        return self._rop(operator.add, value)

    def __mul__(self, value):
        return self._op(operator.mul, value)

    def __rmul__(self, value):
        return self._rop(operator.mul, value)


class Arithemtic(Commutative):

    def __add__(self, i):
        return self._op(operator.add, i)

    def __radd__(self, i):
        return self._rop(operator.add, i)

    def __mul__(self, i):
        return self._op(operator.mul, i)

    def __rmul__(self, i):
        return self._rop(operator.mul, i)

    def __sub__(self, i):
        return self._op(operator.sub, i)

    def __rsub__(self, i):
        return self._rop(operator.sub, i)

    def __floordiv__(self, i):
        return self._op(operator.floordiv, i)

    def __rfloordiv__(self, i):
        return self._rop(operator.floordiv, i)

    def __mod__(self, i):
        return self._op(operator.mod, i)

    def __rmod__(self, i):
        return self._rop(operator.mod, i)

    def __divmod__(self, i):
        return self._op(operator.divmod, i)

    def __rdivmod__(self, i):
        return self._rop(operator.divmod, i)

    def __pow__(self, value, modulo):
        return self._op(operator.pow, i)

    def __rpow__(self, value, modulo):
        return self._rop(operator.pow, i)

    def __lshift__(self, i):
        return self._op(operator.lshift, i)

    def __rlshift__(self, i):
        return self._rop(operator.lshift, i)

    def __rshift__(self, i):
        return self._op(operator.rshift, i)

    def __rrshift__(self, i):
        return self._rop(operator.rshift, i)

    def __and__(self, i):
        return self._op(operator.and_, i)

    def __rand__(self, i):
        return self._rop(operator.and_, i)

    def __xor__(self, i):
        return self._op(operator.xor, i)

    def __rxor__(self, i):
        return self._rop(operator.xor, i)

    def __or__(self, i):
        return self._op(operator.or_, i)

    def __ror__(self, i):
        return self._rop(operator.or_, i)


class List(Commutative):

    @property
    def value(self):
        return self[:]

    @value.setter
    def value(self, value):
        self.extend(value)

    def __iadd__(self, l):
        self.extend(self._to_value(l))
        return self

    def __imul__(self, i):
        self.list_multiply(i)
        return self

    def __len__(self):
        return self.llen()

    def __setitem__(self, i, value):
        try:
            self.lset(i, value)
        except redis.exceptions.ResponseError:
            raise IndexError

    def __getitem__(self, i):
        if isinstance(i, slice):
            start = i.start if i.start is not None else 0
            stop = i.stop if i.stop is not None else 0
            return self.lrange(start, stop - 1)
        item = self.lindex(i)
        if item is None:
            raise IndexError
        return item

    def __delitem__(self, i):
        self.pop(i)

    def extend(self, l):
        self.rpush(*l)

    def append(self, value):
        self.extend([value])

    def insert(self, i, value):
        self.list_insert(i, value)

    def pop(self, i=-1):
        if i == -1:
            return self.rpop()
        elif i == 0:
            return self.lpop()
        else:
            return self.list_pop(i)

    def reverse(self):
        self.list_reverse()

    def index(self, value):
        return self.value.index(value)

    def count(self, value):
        return self.value.count(value)

    def sort(self, reverse=False):
        self._dispatch("sort")(desc=reverse, store=self.key, alpha=True)


class Set(Base):

    @property
    def value(self):
        return self.smembers()

    @value.setter
    def value(self, value):
        self.update(value)

    def _all_redis(self, values):
        return all([isinstance(value, self.__class__) for value in values])

    def _to_keys(self, values):
        return [value.key for value in values]

    def add(self, value):
        self.update([value])

    def update(self, *values):
        self.sadd(*reduce(operator.or_, values))

    def pop(self):
        return self.spop()

    def clear(self):
        self.delete()

    def remove(self, value):
        if self.srem(value) == 0:
            raise KeyError(value)

    def discard(self, value):
        try:
            self.remove(value)
        except KeyError:
            pass

    def __len__(self):
        return self.scard()

    def __contains__(self, value):
        return self.sismember(value)

    def __and__(self, value):
        return self.intersection(value)

    def __iand___(self, value):
        self.intersection_update(value)
        return self

    def __rand__(self, value):
        return self._rop(operator.and_, value)

    def intersection(self, *values):
        if self._all_redis(values):
            return self.sinter(*self._to_keys(values))
        else:
            return reduce(operator.and_, (self.value,) + values)

    def intersection_update(self, *values):
        if self._all_redis(values):
            self.sinterstore(self.key, *self._to_keys(values))
        else:
            values = list(reduce(operator.and_, values))
            self.set_intersection_update(*values)
        return self

    def __or__(self, value):
        return self.union(value)

    def __ior___(self, value):
        self.update(value)
        return self

    def __ror__(self, value):
        return self._rop(operator.or_, value)

    def union(self, *values):
        if self._all_redis(values):
            return self.sunion(*self._to_keys(values))
        else:
            return reduce(operator.or_, (self.value,) + values)

    def __sub__(self, value):
        return self.difference(value)

    def __isub__(self, value):
        self.difference_update(value)
        return self

    def __rsub__(self, value):
        return self._rop(operator.sub, value)

    def difference(self, *values):
        if self._all_redis(values):
            return self.sdiff(*self._to_keys(values))
        else:
            return reduce(operator.sub, (self.value,) + values)

    def difference_update(self, *values):
        if self._all_redis(values):
            self.sdiffstore(self.key, *self._to_keys(values))
        else:
            all_values = [str(uuid.uuid4())]
            for value in values:
                all_values.extend(value)
                all_values.append(all_values[0])
            self.set_difference_update(*all_values)
        return self

    def __xor__(self, value):
        return self.symmetric_difference(value)

    def __ixor__(self, value):
        self.symmetric_difference_update(value)
        return self

    def __rxor__(self, value):
        return self._rop(operator.xor, value)

    def symmetric_difference(self, value):
        if isinstance(value, self.__class__):
            return set(self.set_symmetric_difference("return", value.key))
        else:
            return self.value ^ value

    def symmetric_difference_update(self, value):
        if isinstance(value, self.__class__):
            self.set_symmetric_difference("update", value.key)
        else:
            self.set_symmetric_difference("create", *value)
        return self

    def isdisjoint(self, value):
        return not self.intersection(value)

    def issubset(self, value):
        return self <= value

    def issuperset(self, value):
        return self >= value


class Dict(Base):

    @property
    def value(self):
        return self.hgetall()

    @value.setter
    def value(self, value):
        if not isinstance(value, dict):
            try:
                value = dict(value)
            except TypeError:
                value = None
        if value:
            self.update(value)

    def __len__(self):
        return self.hlen()

    def __contains__(self, name):
        return self.hexists(name)

    def __iter__(self):
        return self.iterkeys()

    def __setitem__(self, name, value):
        self.hset(name, value)

    def __getitem__(self, name):
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value

    def __delitem__(self, name):
        if self.hdel(name) == 0:
            raise KeyError(name)

    def update(self, value):
        self.hmset(value)

    def keys(self):
        return self.hkeys()

    def values(self):
        return self.hvals()

    def items(self):
        return self.value.items()

    def iterkeys(self):
        return iter(self.keys())

    def itervalues(self):
        return iter(self.values())

    def iteritems(self):
        return iter(self.items())

    def setdefault(self, name, value=None):
        if self.hsetnx(name, value) == 1:
            return value
        else:
            return self[name]

    def get(self, name, default=None):
        value = self.hget(name)
        return value if value is not None else default

    def has_key(self, name):
        return name in self

    def copy(self):
        return self.__class__(self.value)

    def clear(self):
        self.delete()

    @classmethod
    def fromkeys(cls, *args):
        if len(args) == 1:
            args += ("",)
        return cls({}.fromkeys(*args))


class String(Commutative):

    @property
    def value(self):
        return self.get()

    @value.setter
    def value(self, value):
        if value:
            self.set(value)

    def __iadd__(self, s):
        self.append(self._to_value(s))
        return self

    def __imul__(self, i):
        self.string_multiply(i)
        return self

    def __len__(self):
        return self.strlen()

    def __setitem__(self, i, value):
        if isinstance(i, slice):
            start = i.start if i.start is not None else 0
            stop = i.stop
        else:
            start = i
            stop = None
        if stop is not None and stop < start + len(value):
            self.string_setitem(start, stop, value)
        else:
            self.setrange(start, value)

    def __getitem__(self, i):
        if not isinstance(i, slice):
            i = slice(i, i + 1)
        start = i.start if i.start is not None else 0
        stop = i.stop if i.stop is not None else 0
        value = self.getrange(start, stop - 1)
        if not value:
            raise IndexError
        return value


class ImmutableString(String):

    def __iadd__(self, s):
        return self + s

    def __imul__(self, i):
        return self * i

    def __setitem__(self, i):
        raise TypeError


class Int(Base):

    @property
    def value(self):
        return int(self.get())

    @value.setter
    def value(self, value):
        if value:
            self.set(value)



    def __isub__(self, i):
        self.decr(i)
        return self


    def __iadd__(self, i):
        self.incr(i)
        return self


    def __imul__(self, i):
        return self



