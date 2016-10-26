##############################################################################
#
# Copyright (c) 2002 Zope Foundation and Contributors.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################
"""
transformer module:

uses Python standard library ast module and its containing classes to transform
the parsed python code to create a modified AST for a byte code generation.
"""

# This package should follow the Plone Sytleguide for Python,
# which differ from PEP8:
# http://docs.plone.org/develop/styleguide/python.html


import ast
import sys


# if any of the ast Classes should not be whitelisted, please comment them out
# and add a comment why.
AST_WHITELIST = [
    # ast for Literals,
    ast.Num,
    ast.Str,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.Ellipsis,
    #ast.NameConstant,
    # ast for Variables,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Del,
    # Expressions,
    ast.Expr,
    ast.UnaryOp,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.Invert,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitAnd,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    ast.Call,
    ast.keyword,
    ast.IfExp,
    ast.Attribute,
    # Subscripting,
    ast.Subscript,
    ast.Index,
    ast.Slice,
    ast.ExtSlice,
    # Comprehensions,
    ast.ListComp,
    ast.SetComp,
    ast.GeneratorExp,
    ast.DictComp,
    ast.comprehension,
    # Statements,
    ast.Assign,
    ast.AugAssign,
    ast.Raise,
    ast.Assert,
    ast.Delete,
    ast.Pass,
    # Imports,
    ast.Import,
    ast.ImportFrom,
    ast.alias,
    # Control flow,
    ast.If,
    ast.For,
    ast.While,
    ast.Break,
    ast.Continue,
    #ast.ExceptHanlder,  # We do not Support ExceptHanlders
    ast.With,
    #ast.withitem,
    # Function and class definitions,
    ast.FunctionDef,
    ast.Lambda,
    ast.arguments,
    #ast.arg,
    ast.Return,
    # ast.Yield, # yield is not supported
    #ast.YieldFrom,
    #ast.Global,
    #ast.Nonlocal,
    ast.ClassDef,
    ast.Module,
    ast.Param
]


# For AugAssign the operator must be converted to a string.
IOPERATOR_TO_STR = {
    # Shared by python2 and python3
    ast.Add: '+=',
    ast.Sub: '-=',
    ast.Mult: '*=',
    ast.Div: '/=',
    ast.Mod: '%=',
    ast.Pow: '**=',
    ast.LShift: '<<=',
    ast.RShift: '>>=',
    ast.BitOr: '|=',
    ast.BitXor: '^=',
    ast.BitAnd: '&=',
    ast.FloorDiv: '//='
}


version = sys.version_info
if version >= (2, 7) and version < (2, 8):
    AST_WHITELIST.extend([
        ast.Print,
        ast.Raise,
        ast.TryExcept,
        ast.TryFinally,
        ast.ExceptHandler
    ])

if version >= (3, 0):
    AST_WHITELIST.extend([
        ast.Bytes,
        ast.Starred,
        ast.arg,
        ast.Try,
        ast.ExceptHandler
    ])

if version >= (3, 4):
    AST_WHITELIST.extend([
    ])

if version >= (3, 5):
    IOPERATOR_TO_STR[ast.MatMult] = '@='

    AST_WHITELIST.extend([
        ast.MatMult,
        # Async und await,  # No Async Elements should be supported
        #ast.AsyncFunctionDef,  # No Async Elements should be supported
        #ast.Await,  # No Async Elements should be supported
        #ast.AsyncFor,  # No Async Elements should be supported
        #ast.AsyncWith,  # No Async Elements should be supported
    ])

if version >= (3, 6):
    AST_WHITELIST.extend([
    ])


# When new ast nodes are generated they have no 'lineno' and 'col_offset'.
# This function copies these two fields from the incoming node
def copy_locations(new_node, old_node):
    assert 'lineno' in new_node._attributes
    new_node.lineno = old_node.lineno

    assert 'col_offset' in new_node._attributes
    new_node.col_offset = old_node.col_offset

    ast.fix_missing_locations(new_node)




class RestrictingNodeTransformer(ast.NodeTransformer):

    def __init__(self, errors=[], warnings=[], used_names=[]):
        super(RestrictingNodeTransformer, self).__init__()
        self.errors = errors
        self.warnings = warnings
        self.used_names = used_names

        # Global counter to construct temporary variable names.
        self._tmp_idx = 0

    def gen_tmp_name(self):
        # 'check_name' ensures that no variable is prefixed with '_'.
        # => Its safe to use '_tmp..' as a temporary variable.
        name = '_tmp%i' % self._tmp_idx
        self._tmp_idx +=1
        return name

    def error(self, node, info):
        """Record a security error discovered during transformation."""
        lineno = getattr(node, 'lineno', None)
        self.errors.append('Line {lineno}: {info}'.format(lineno=lineno, info=info))

    def warn(self, node, info):
        """Record a security error discovered during transformation."""
        lineno = getattr(node, 'lineno', None)
        self.warnings.append('Line {lineno}: {info}'.format(lineno=lineno, info=info))

    def use_name(self, node, info):
        """Record a security error discovered during transformation."""
        lineno = getattr(node, 'lineno', None)
        self.used_names.append('Line {lineno}: {info}'.format(lineno=lineno, info=info))

    def guard_iter(self, node):
        """
        Converts:
            for x in expr
        to
            for x in _getiter_(expr)

        Also used for
        * list comprehensions
        * dict comprehensions
        * set comprehensions
        * generator expresions
        """
        node = self.generic_visit(node)

        new_iter = ast.Call(
            func=ast.Name("_getiter_", ast.Load()),
            args=[node.iter],
            keywords=[])

        copy_locations(new_iter, node.iter)
        node.iter = new_iter
        return node

    def gen_none_node(self):
        if version >= (3, 4):
            return ast.NameConstant(value=None)
        else:
            return ast.Name(id='None', ctx=ast.Load())

    def gen_lambda(self, args, body):
        return ast.Lambda(
            args=ast.arguments(args=args, vararg=None, kwarg=None, defaults=[]),
            body=body)

    def gen_del_stmt(self, name_to_del):
        return ast.Delete(targets=[ast.Name(name_to_del, ast.Del())])

    def gen_try_finally(self, body, finalbody):
        if version.major == 2:
            return ast.TryFinally(body=body, finalbody=finalbody)

        else:
            return ast.Try(
                body=body,
                handlers=[],
                orelse=[],
                finalbody=finalbody)


    def transform_slice(self, slice_):
        """Transforms slices into function parameters.

        ast.Slice nodes are only allowed within a ast.Subscript node.
        To use a slice as an argument of ast.Call it has to be converted.
        Conversion is done by calling the 'slice' function from builtins
        """

        if isinstance(slice_, ast.Index):
            return slice_.value

        elif isinstance(slice_, ast.Slice):
            # Create a python slice object.
            args = []

            if slice_.lower:
                args.append(slice_.lower)
            else:
                args.append(self.gen_none_node())

            if slice_.upper:
                args.append(slice_.upper)
            else:
                args.append(self.gen_none_node())

            if slice_.step:
                args.append(slice_.step)
            else:
                args.append(self.gen_none_node())

            return ast.Call(
                func=ast.Name('slice', ast.Load()),
                args=args,
                keywords=[])

        elif isinstance(slice_, ast.ExtSlice):
            dims = ast.Tuple([], ast.Load())
            for item in slice_.dims:
                dims.elts.append(self.transform_slice(item))
            return dims

        else:
            raise Exception("Unknown slice type: {0}".format(slice_))

    def check_name(self, node, name):
        if name is None:
            return

        if name.startswith('_') and name != '_':
            self.error(
                node,
                '"{name}" is an invalid variable name because it '
                'starts with "_"'.format(name=name))

        elif name.endswith('__roles__'):
            self.error(node, '"%s" is an invalid variable name because '
                       'it ends with "__roles__".' % name)

        elif name == "printed":
            self.error(node, '"printed" is a reserved name.')

    # Boha yeah, there are two different ways to unpack tuples.
    # Way 1: 'transform_tuple_assign'.
    #  This transforms tuple unpacking via multiple statements.
    #  Pro: Can be used in python2 and python3
    #  Con: statements can *NOT* be used in expressions.
    #       Unfortunately lambda parameters in python2 can have tuple parameters
    #       too, which must be unpacked as well. However lambda bodies allow
    #       only expressions.
    #       => This way cannot be used to unpack tuple parameters in lambdas.
    # Way 2: 'transform_tuple_unpack'
    #  This transforms tuple unpacking by using nested lambdas.
    #  Pro: Implemented by using expressions only.
    #       => can be used to unpack tuple parameters in lambdas.
    #  Con: Not usable in python3
    # So the second way is only needed for unpacking of tuple parameters on
    # lambda functions. Luckily tuple parameters are gone in python3.
    # So way 2 is needed in python2 only.

    def transform_tuple_assign(self, target, value):
        """Protects tuple unpacking with _getiter_ by using multiple statements.

        Works in python2 and python3, but does not help if only expressions are
        allowed.

        (a, b) = value
        becomes:
        (a, b) = _getiter_(value)

        (a, (b, c)) = value
        becomes:

        (a, t1) = _getiter_(value)
        try:
            (b, c) = _getiter_(t1)
        finally:
            del t1
        """

        # Finds all the child tuples and give them temporary names
        child_tuples = []
        new_target = []
        for el in target.elts:
            if isinstance(el, ast.Tuple):
                tmp_name = self.gen_tmp_name()
                new_target.append(ast.Name(tmp_name, ast.Store()))
                child_tuples.append((tmp_name, el))
            else:
                new_target.append(el)

        unpacks = []

        # Protect target via '_getiter_'
        wrap = ast.Assign(
            targets=[ast.Tuple(new_target, ast.Store())],
            value=ast.Call(
                func=ast.Name('_getiter_', ast.Load()),
                args=[value],
                keywords=[]
            )
        )

        unpacks.append(wrap)

        # unpack the child tuples and cleanup the temporary names.
        for tmp_name, child in child_tuples:
            src = ast.Name(tmp_name, ast.Load())
            unpacks.append(
                self.gen_try_finally(
                    self.transform_tuple_assign(child, src),
                    [self.gen_del_stmt(tmp_name)])
            )

        return unpacks

    def transform_tuple_unpack(self, root, src, to_wrap=None):
        """Protects tuple unpacking with _getiter_ by using expressions only.

        Works only in python2.

        root: is the original tuple to unpack
        src: ast node where the tuple to unpack should be loaded
        to_wrap: set of (child) tuples of root which sould be unpacked

        It becomes complicated when you think about nested unpacking.
        For example '(a, (b, (d, e)), (x,z))'

        For each of this tuple (from the outside to the inside) _getiter_ must
        be called. The following illustrates what this function constructs to
        solve this:

        l0 = _getiter_(x)
        l1 = lambda (a, t0, t1): (a, _getiter_(t0), _getiter_(t1))
        l2 = lambda (a, (b, t2), (x, z)): (a, (b, _getiter(t2)), (x, z))

        Return value: l2(l1(l0(<src>)))
        """

        if to_wrap is None:
            to_wrap = {root}
        elif not to_wrap:
            return

        # Generate a wrapper for the current level of tuples to wrap/unpack.
        wrapper_param, wrapper_body = self.gen_tuple_wrapper(root, to_wrap)

        # In the end wrapper is a callable with one argument.
        # If the body is not a callable its wrapped with a lambda
        if isinstance(wrapper_body, ast.Call):
            wrapper = ast.Call(func=wrapper_body.func, args=[src], keywords=[])
        else:
            wrapper = self.gen_lambda([wrapper_param], wrapper_body)
            wrapper = ast.Call(func=wrapper, args=[src], keywords=[])

        # Check if the elements of the current tuple are tuples again (nested).
        child_tuples = self.find_tuple_childs(root, to_wrap)
        if not child_tuples:
            return wrapper

        return self.transform_tuple_unpack(root, wrapper, child_tuples)

    def gen_tuple_wrapper(self, parent, to_wrap):
        """Constructs the parameter and body to unpack the tuples in 'to_wrap'

        Helper method of 'transform_tuple_unpack'.

        For example the 'root' tuple is
        (a, (b, (d, e)), (x,z))'
        and the 'to_wrap' is (d, e) the return value is
        param = (a, (b, t2), (x, z))
        body = (a, (b, _getiter(t2)), (x, z))
        """
        if parent in to_wrap:
            name = self.gen_tmp_name()
            param = ast.Name(name, ast.Param())
            body = ast.Call(
                func=ast.Name('_getiter_', ast.Load()),
                args=[ast.Name(name, ast.Load())],
                keywords=[])

        elif isinstance(parent, ast.Name):
            param = ast.Name(parent.id, ast.Param())
            body = ast.Name(parent.id, ast.Load())

        elif isinstance(parent, ast.Tuple):
            param = ast.Tuple([], ast.Store())
            body = ast.Tuple([], ast.Load())
            for c in parent.elts:
                c_param, c_body = self.gen_tuple_wrapper(c, to_wrap)
                c_param.ctx = ast.Store()
                param.elts.append(c_param)
                body.elts.append(c_body)
        else:
            raise Exception("Cannot handle node %" % parent)

        return param, body

    def find_tuple_childs(self, parent, to_wrap):
        """Finds child tuples of the 'to_wrap' nodes.

        Helper method of 'transform_tuple_unpack'.
        """
        childs = set()

        if parent in to_wrap:
            childs.update(c for c in parent.elts if isinstance(c, ast.Tuple))

        elif isinstance(parent, ast.Tuple):
            for c in parent.elts:
                childs.update(self.find_tuple_childs(c, to_wrap))

        return childs

    def check_function_argument_names(self, node):
        # In python3 arguments are always identifiers.
        # In python2 the 'Python.asdl' specifies expressions, but
        # the python grammer allows only identifiers or a tuple of
        # identifiers. If its a tuple 'tuple parameter unpacking' is used,
        # which is gone in python3.
        # See https://www.python.org/dev/peps/pep-3113/

        if version.major == 2:
            # Needed to handle nested 'tuple parameter unpacking'.
            # For example 'def foo((a, b, (c, (d, e)))): pass'
            to_check = list(node.args.args)
            while to_check:
                item = to_check.pop()
                if isinstance(item, ast.Tuple):
                    to_check.extend(item.elts)
                else:
                    self.check_name(node, item.id)

            self.check_name(node, node.args.vararg)
            self.check_name(node, node.args.kwarg)

        else:
            for arg in node.args.args:
                self.check_name(node, arg.arg)

            if node.args.vararg:
                self.check_name(node, node.args.vararg.arg)

            if node.args.kwarg:
                self.check_name(node, node.args.kwarg.arg)

            for arg in node.args.kwonlyargs:
                self.check_name(node, arg.arg)

    # Special Functions for an ast.NodeTransformer

    def generic_visit(self, node):
        if node.__class__ not in AST_WHITELIST:
            self.error(
                node,
                '{0.__class__.__name__} statements are not allowed.'.format(
                    node))
        else:
            return super(RestrictingNodeTransformer, self).generic_visit(node)

    ##########################################################################
    # visti_*ast.ElementName* methods are used to eigther inspect special
    # ast Modules or modify the behaviour
    # therefore please have for all existing ast modules of all python versions
    # that should be supported included.
    # if nothing is need on that element you could comment it out, but please
    # let it remain in the file and do document why it is uncritical.
    # RestrictedPython is a very complicated peace of software and every
    # maintainer needs a way to understand why something happend here.
    # Longish code with lot of comments are better than ununderstandable code.
    ##########################################################################

    # ast for Literals

    def visit_Num(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Str(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Bytes(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_List(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Tuple(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Set(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Dict(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Ellipsis(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_NameConstant(self, node):
        """

        """
        return self.generic_visit(node)

    # ast for Variables

    def visit_Name(self, node):
        """

        """
        self.check_name(node, node.id)
        return self.generic_visit(node)

    def visit_Load(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Store(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Del(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Starred(self, node):
        """

        """
        return self.generic_visit(node)

    # Expressions

    def visit_UnaryOp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_UAdd(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_USub(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Not(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Invert(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_BinOp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Add(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Sub(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Div(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_FloorDiv(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Mod(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Pow(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_LShift(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_RShift(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_BitOr(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_BitAnd(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_MatMult(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_BoolOp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_And(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Or(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Compare(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Eq(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_NotEq(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Lt(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_LtE(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Gt(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_GtE(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Is(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_IsNot(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_In(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_NotIn(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Call(self, node):
        """Checks calls with '*args' and '**kwargs'.

        Note: The following happens only if '*args' or '**kwargs' is used.

        Transfroms 'foo(<all the possible ways of args>)' into
        _apply_(foo, <all the possible ways for args>)

        The thing is that '_apply_' has only '*args', '**kwargs', so it gets
        Python to collapse all the myriad ways to call functions
        into one manageable from.

        From there, '_apply_()' wraps args and kws in guarded accessors,
        then calls the function, returning the value.
        """

        if isinstance(node.func, ast.Name):
            if node.func.id == 'exec':
                self.error(node, 'Exec calls are not allowed.')
            elif node.func.id == 'eval':
                self.error(node, 'Eval calls are not allowed.')

        needs_wrap = False

        # In python2.7 till python3.4 '*args', '**kwargs' have dedicated
        # attributes on the ast.Call node.
        # In python 3.5 and greater this has changed due to the fact that
        # multiple '*args' and '**kwargs' are possible.
        # '*args' can be detected by 'ast.Starred' nodes.
        # '**kwargs' can be deteced by 'keyword' nodes with 'arg=None'.

        if version < (3, 5):
            if (node.starargs is not None) or (node.kwargs is not None):
                needs_wrap = True
        else:
            for pos_arg in node.args:
                if isinstance(pos_arg, ast.Starred):
                    needs_wrap = True

            for keyword_arg in node.keywords:
                if keyword_arg.arg is None:
                    needs_wrap = True

        node = self.generic_visit(node)

        if not needs_wrap:
            return node

        node.args.insert(0, node.func)
        node.func = ast.Name('_apply_', ast.Load())
        copy_locations(node.func, node.args[0])
        return node

    def visit_keyword(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_IfExp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Attribute(self, node):
        """Checks and mutates attribute access/assignment.

        'a.b' becomes '_getattr_(a, "b")'

        'a.b = c' becomes '_write_(a).b = c'
        The _write_ function should return a security proxy.
        """
        if node.attr.startswith('_') and node.attr != '_':
            self.error(
                node,
                '"{name}" is an invalid attribute name because it starts '
                'with "_".'.format(name=node.attr))

        if node.attr.endswith('__roles__'):
            self.error(
                node,
                '"{name}" is an invalid attribute name because it ends '
                'with "__roles__".'.format(name=node.attr))

        if isinstance(node.ctx, ast.Load):
            node = self.generic_visit(node)
            new_node = ast.Call(
                func=ast.Name('_getattr_', ast.Load()),
                args=[node.value, ast.Str(node.attr)],
                keywords=[])

            copy_locations(new_node, node)
            return new_node

        elif isinstance(node.ctx, ast.Store):
            node = self.generic_visit(node)
            new_value = ast.Call(
                func=ast.Name('_write_', ast.Load()),
                args=[node.value],
                keywords=[])

            copy_locations(new_value, node.value)
            node.value = new_value
            return node

        else:
            return self.generic_visit(node)

    # Subscripting

    def visit_Subscript(self, node):
        """Transforms all kinds of subscripts.

        'foo[bar]' becomes '_getitem_(foo, bar)'
        'foo[:ab]' becomes '_getitem_(foo, slice(None, ab, None))'
        'foo[ab:]' becomes '_getitem_(foo, slice(ab, None, None))'
        'foo[a:b]' becomes '_getitem_(foo, slice(a, b, None))'
        'foo[a:b:c]' becomes '_getitem_(foo, slice(a, b, c))'
        'foo[a, b:c] becomes '_getitem_(foo, (a, slice(b, c, None)))'
        'foo[a] = c' becomes '_write(foo)[a] = c'
        'del foo[a]' becomes 'del _write_(foo)[a]'

        The _write_ function should return a security proxy.
        """
        node = self.generic_visit(node)

        # 'AugStore' and 'AugLoad' are defined in 'Python.asdl' as possible
        # 'expr_context'. However, according to Python/ast.c
        # they are NOT used by the implementation => No need to worry here.
        # Instead ast.c creates 'AugAssign' nodes, which can be visited.

        if isinstance(node.ctx, ast.Load):
            new_node = ast.Call(
                func=ast.Name('_getitem_', ast.Load()),
                args=[node.value, self.transform_slice(node.slice)],
                keywords=[])

            copy_locations(new_node, node)
            return new_node

        elif isinstance(node.ctx, (ast.Del, ast.Store)):
            new_value = ast.Call(
                func=ast.Name('_write_', ast.Load()),
                args=[node.value],
                keywords=[])

            copy_locations(new_value, node)
            node.value = new_value
            return node

        else:
            return node

    def visit_Index(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Slice(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_ExtSlice(self, node):
        """

        """
        return self.generic_visit(node)

    # Comprehensions

    def visit_ListComp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_SetComp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_GeneratorExp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_DictComp(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_comprehension(self, node):
        """

        """
        return self.guard_iter(node)

    # Statements

    def visit_Assign(self, node):
        """

        """

        node = self.generic_visit(node)

        if not any(isinstance(t, ast.Tuple) for t in node.targets):
            return node

        # Handle sequence unpacking.
        # For briefness this example omits cleanup of the temporary variables.
        # Check 'transform_tuple_assign' how its done.
        #
        # - Single target (with nested support)
        # (a, (b, (c, d))) = <exp>
        # is converted to
        # (a, t1) = _getiter_(<exp>)
        # (b, t2) = _getiter_(t1)
        # (c, d) = _getiter_(t2)
        #
        # - Multi targets
        # (a, b) = (c, d) = <exp>
        # is converted to
        # (c, d) = _getiter_(<exp>)
        # (a, b) = _getiter_(<exp>)
        # Why is this valid ? The original bytecode for this multi targets
        # behaves the same way.

        # ast.NodeTransformer works with list results.
        # He injects it at the right place of the node's parent statements.
        new_nodes = []

        # python fills the right most target first.
        for target in reversed(node.targets):
            if isinstance(target, ast.Tuple):
                wrappers = self.transform_tuple_assign(target, node.value)
                new_nodes.extend(wrappers)
            else:
                new_node = ast.Assign(targets=[target], value=target.value)
                new_nodes.append(new_node)

        for new_node in new_nodes:
            copy_locations(new_node, node)

        return new_nodes

    def visit_AugAssign(self, node):
        """Forbid certain kinds of AugAssign

        According to the language reference (and ast.c) the following nodes
        are are possible:
        Name, Attribute, Subscript

        Note that although augmented assignment of attributes and
        subscripts is disallowed, augmented assignment of names (such
        as 'n += 1') is allowed.
        'n += 1' becomes 'n = _inplacevar_("+=", n, 1)'
        """

        node = self.generic_visit(node)

        if isinstance(node.target, ast.Attribute):
            self.error(
                node,
                "Augmented assignment of attributes is not allowed.")
            return node

        elif isinstance(node.target, ast.Subscript):
            self.error(
                node,
                "Augmented assignment of object items "
                "and slices is not allowed.")
            return node

        elif isinstance(node.target, ast.Name):
            new_node = ast.Assign(
                targets=[node.target],
                value=ast.Call(
                    func=ast.Name('_inplacevar_', ast.Load()),
                    args=[
                        ast.Str(IOPERATOR_TO_STR[type(node.op)]),
                        ast.Name(node.target.id, ast.Load()),
                        node.value
                    ],
                    keywords=[]))

            copy_locations(new_node, node)
            return new_node

        return node

    def visit_Print(self, node):
        """
        Fields:
        * dest (optional)
        * value --> List of Nodes
        * nl --> newline (True or False)
        """
        if node.dest is not None:
            self.error(
                node,
                'print statements with destination / chevron are not allowed.')

    def visit_Raise(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Assert(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Delete(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Pass(self, node):
        """

        """
        return self.generic_visit(node)

    # Imports

    def visit_Import(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_alias(self, node):
        """

        """
        return self.generic_visit(node)

    # Control flow

    def visit_If(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_For(self, node):
        """

        """
        return self.guard_iter(node)

    def visit_While(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Break(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Continue(self, node):
        """

        """
        return self.generic_visit(node)

#    def visit_Try(self, node):
#        """
#
#        """
#        return self.generic_visit(node)

#    def visit_TryFinally(self, node):
#        """
#
#        """
#        return self.generic_visit(node)

#    def visit_TryExcept(self, node):
#        """
#
#        """
#        return self.generic_visit(node)

#    def visit_ExceptHandler(self, node):
#        """
#
#        """
#        return self.generic_visit(node)

    def visit_With(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_withitem(self, node):
        """

        """
        return self.generic_visit(node)

    # Function and class definitions

    def visit_FunctionDef(self, node):
        """Checks a function defintion.

        Checks the name of the function and the arguments.
        """

        self.check_name(node, node.name)
        self.check_function_argument_names(node)

        node = self.generic_visit(node)

        if version.major == 3:
            return node

        # Protect 'tuple parameter unpacking' with '_getiter_'.

        unpacks = []
        for index, arg in enumerate(list(node.args.args)):
            if isinstance(arg, ast.Tuple):
                tmp_name = self.gen_tmp_name()

                # converter looks like wrapper(tmp_name).
                # Wrapper takes care to protect
                # sequence unpacking with _getiter_
                converter = self.transform_tuple_unpack(
                        arg,
                        ast.Name(tmp_name, ast.Load()))

                # Generates:
                # try:
                #     # converter is 'wrapper(tmp_name)'
                #     arg = converter
                # finally:
                #     del tmp_arg
                cleanup = ast.TryFinally(
                    body=[ast.Assign(targets=[arg], value=converter)],
                    finalbody=[self.gen_del_stmt(tmp_name)]
                )

                # Replace the tuple with a single (temporary) parameter.
                node.args.args[index] = ast.Name(tmp_name, ast.Param())

                copy_locations(node.args.args[index], node)
                copy_locations(cleanup, node)
                unpacks.append(cleanup)

        # Add the unpacks at the front of the body.
        # Keep the order, so that tuple one is unpacked first.
        node.body[0:0] = unpacks
        return node

    def visit_Lambda(self, node):
        """Checks a lambda definition."""
        self.check_function_argument_names(node)

        node = self.generic_visit(node)

        if version.major == 3:
            return node

        # Check for tuple parameters which need _getiter_ protection
        if not any(isinstance(arg, ast.Tuple) for arg in node.args.args):
            return node

        # Wrap this lambda function with another. Via this wrapping it is
        # possible to protect the 'tuple arguments' with _getiter_
        outer_params = []
        inner_args = []

        for arg in node.args.args:
            if isinstance(arg, ast.Tuple):
                tmp_name = self.gen_tmp_name()
                converter = self.transform_tuple_unpack(
                    arg,
                    ast.Name(tmp_name, ast.Load()))

                outer_params.append(ast.Name(tmp_name, ast.Param()))
                inner_args.append(converter)

            else:
                outer_params.append(arg)
                inner_args.append(ast.Name(arg.id, ast.Load()))

        body = ast.Call(func=node, args=inner_args, keywords=[])
        new_node = self.gen_lambda(outer_params, body)

        if node.args.vararg:
            new_node.args.vararg = node.args.vararg
            body.starargs = ast.Name(node.args.vararg, ast.Load())

        if node.args.kwarg:
            new_node.args.kwarg = node.args.kwarg
            body.kwargs = ast.Name(node.args.kwarg, ast.Load())

        copy_locations(new_node, node)
        return new_node

    def visit_arguments(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_arg(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Return(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Yield(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_YieldFrom(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Global(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Nonlocal(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_ClassDef(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Module(self, node):
        """

        """
        return self.generic_visit(node)

    # Async und await

    def visit_AsyncFunctionDef(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_Await(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_AsyncFor(self, node):
        """

        """
        return self.generic_visit(node)

    def visit_AsyncWith(self, node):
        """

        """
        return self.generic_visit(node)
