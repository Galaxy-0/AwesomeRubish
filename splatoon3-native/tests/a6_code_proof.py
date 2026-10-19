"""Compare an operation and its referenced helpers/constants across snapshots.

Like A4's accepted damage reuse, unrelated controller changes do not invalidate
an unchanged operation. Eager nonliteral state and dynamic global lookup refuse
reuse. A whole-file hash match remains the preferred proof.
"""
import ast
import hashlib


def operation_digest(source,roots):
    tree=ast.parse(source);definitions={};imports=[];constants={}
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):imports.append(node)
        elif isinstance(node,(ast.FunctionDef,ast.ClassDef)):definitions[node.name]=node
        elif isinstance(node,ast.Assign) and all(isinstance(t,ast.Name) for t in node.targets):
            value=ast.literal_eval(node.value)
            for target in node.targets:definitions[target.id]=node;constants[target.id]=value
        elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):pass
        else:raise ValueError('nonliteral module state prevents operation reuse')
    # Function defaults execute at import time even when a function is unused.
    for node in ast.walk(tree):
        if isinstance(node,ast.FunctionDef):
            if node.decorator_list:raise ValueError('decorated function requires whole-module proof')
            for default in node.args.defaults+[v for v in node.args.kw_defaults if v is not None]:
                if isinstance(default,ast.Name) and default.id in constants:continue
                ast.literal_eval(default)
        if isinstance(node,ast.ClassDef):
            if node.bases or node.keywords or any(not isinstance(d,ast.Name) or d.id!='dataclass' for d in node.decorator_list):
                raise ValueError('dynamic class construction prevents reuse')
            for member in node.body:
                if isinstance(member,(ast.FunctionDef,ast.Pass)):continue
                if isinstance(member,ast.AnnAssign):
                    if member.value is not None:ast.literal_eval(member.value)
                elif isinstance(member,ast.Expr) and isinstance(member.value,ast.Constant) and isinstance(member.value.value,str):pass
                else:raise ValueError('eager class state prevents operation reuse')
    selected=set();pending=list(roots)
    while pending:
        name=pending.pop()
        if name in selected:continue
        if name not in definitions:raise ValueError('missing operation definition: '+name)
        selected.add(name)
        for item in ast.walk(definitions[name]):
            if isinstance(item,ast.Name):
                if item.id in {'globals','locals','eval','exec','getattr','setattr','delattr','__import__'}:
                    raise ValueError('dynamic global lookup prevents operation reuse')
                if item.id in definitions and item.id not in selected:pending.append(item.id)
    nodes=[node for node in tree.body if any(node is definitions[name] for name in selected)]
    normalized=ast.dump(ast.Module(body=imports+nodes,type_ignores=[]),include_attributes=False)
    return hashlib.sha256(normalized.encode()).hexdigest()
