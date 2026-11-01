"""Parse and authorize read queries before sending them to MySQL."""
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
from sqlalchemy import inspect
from app.database.connection import engine


def prepare_sql(sql_query, user_tables):
    """Resolve table identifiers structurally, without rewriting literals or aliases."""
    statements = sqlglot.parse(sql_query, read="mysql")
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("Exactly one SELECT statement is required.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise ValueError("Only SELECT queries are allowed.")
    blocked = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
               exp.Alter, exp.Command, exp.Into, exp.Lock, exp.PropertyEQ, exp.Parameter)
    if any(isinstance(node, blocked) for node in tree.walk()):
        raise ValueError("Write operations, file output, and locking reads are forbidden.")
    for node in tree.walk():
        if isinstance(node, exp.Func):
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            if name.upper() in {"SLEEP", "BENCHMARK", "LOAD_FILE", "GET_LOCK", "RELEASE_LOCK"}:
                raise ValueError("This SQL function is not permitted.")
    allowed = {t.lower(): t for t in user_tables}
    friendly = {}
    for table in user_tables:
        friendly.setdefault(table.split("_usr_")[0].lower(), []).append(table)
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if not isinstance(source, exp.Table):
                continue
            if source.db or source.catalog:
                raise ValueError("Cross-database references are not allowed.")
            name = source.name.lower()
            physical = allowed.get(name)
            if physical is None and len(friendly.get(name, [])) == 1:
                physical = friendly[name][0]
            if physical is None:
                raise ValueError(f"Access to table '{source.name}' is forbidden.")
            if physical != source.name:
                if not source.alias:
                    source.set("alias", exp.TableAlias(this=exp.to_identifier(source.name, quoted=True)))
                source.set("this", exp.to_identifier(physical, quoted=True))
    inspector = inspect(engine)
    schema = {
        table.lower(): {c["name"].lower(): "UNKNOWN" for c in inspector.get_columns(table)}
        for table in user_tables
    }
    # MySQL column names are case insensitive even when backtick quoted.
    validation_tree = tree.copy()
    for identifier in validation_tree.find_all(exp.Identifier):
        identifier.set("this", identifier.this.lower())
    qualify(validation_tree, dialect="mysql", schema=schema, expand_stars=False,
            validate_qualify_columns=True)
    return tree.sql(dialect="mysql")


def validate_sql(sql_query, user_tables):
    try:
        prepare_sql(sql_query, user_tables)
        return True, "SQL is valid."
    except Exception as exc:
        return False, str(exc)
