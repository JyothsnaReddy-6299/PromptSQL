import ast
import re
from typing import List, Tuple, Set


class SafeExpressionValidator(ast.NodeVisitor):
    """
    Validates that a metric expression contains ONLY safe arithmetic operations
    over authorized column names and numeric constants.
    Rejects any function calls, variable assignments, attribute accesses, or injections.
    """

    ALLOWED_NODES = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.UAdd,
        ast.Constant,
        ast.Name,
    )

    def __init__(self, allowed_columns: Set[str]):
        super().__init__()
        # Store allowed columns as lowercase for case-insensitive matching
        self.allowed_columns_map = {col.lower(): col for col in allowed_columns}
        self.referenced_columns: List[str] = []

    def generic_visit(self, node):
        if not isinstance(node, self.ALLOWED_NODES):
            raise ValueError(f"Expression contains forbidden element: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Constant(self, node):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Only numeric constants are allowed in metric expressions, got {type(node.value).__name__}")

    def visit_Name(self, node):
        col_lower = node.id.lower()
        if col_lower not in self.allowed_columns_map:
            raise ValueError(
                f"Column '{node.id}' in expression does not exist in dataset schema. "
                f"Allowed columns: {', '.join(sorted(self.allowed_columns_map.values()))}"
            )
        # Record canonical column name
        canonical = self.allowed_columns_map[col_lower]
        if canonical not in self.referenced_columns:
            self.referenced_columns.append(canonical)


def _ast_to_sql(node: ast.AST, col_map: dict) -> str:
    """
    Compiles an AST node into safe, escaped SQL.
    """
    if isinstance(node, ast.Expression):
        return _ast_to_sql(node.body, col_map)
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Name):
        canonical = col_map[node.id.lower()]
        return f"`{canonical}`"
    elif isinstance(node, ast.UnaryOp):
        operand_sql = _ast_to_sql(node.operand, col_map)
        if isinstance(node.op, ast.USub):
            return f"(-{operand_sql})"
        elif isinstance(node.op, ast.UAdd):
            return f"(+{operand_sql})"
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
    elif isinstance(node, ast.BinOp):
        left_sql = _ast_to_sql(node.left, col_map)
        right_sql = _ast_to_sql(node.right, col_map)
        if isinstance(node.op, ast.Add):
            return f"({left_sql} + {right_sql})"
        elif isinstance(node.op, ast.Sub):
            return f"({left_sql} - {right_sql})"
        elif isinstance(node.op, ast.Mult):
            return f"({left_sql} * {right_sql})"
        elif isinstance(node.op, ast.Div):
            # Guard against division by zero in SQL
            return f"({left_sql} / NULLIF({right_sql}, 0))"
        raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
    raise ValueError(f"Cannot compile AST node: {type(node).__name__}")


def validate_and_compile_expression(
    expression: str,
    allowed_columns: List[str],
    aggregation: str = "SUM"
) -> Tuple[str, List[str]]:
    """
    Validates a metric expression against allowed dataset columns and compiles it to SQL.
    Returns:
        (compiled_sql, list_of_referenced_columns)

    Examples:
        expression: "Unit_Price * Quantity_Ordered", aggregation: "SUM"
        -> ("SUM(`Unit_Price` * `Quantity_Ordered`)", ["Unit_Price", "Quantity_Ordered"])

        expression: "Total_Sales", aggregation: "SUM"
        -> ("SUM(`Total_Sales`)", ["Total_Sales"])

        expression: "id", aggregation: "COUNT"
        -> ("COUNT(`id`)", ["id"])
    """
    if not expression or not expression.strip():
        raise ValueError("Metric expression cannot be empty.")

    expr_clean = expression.strip()

    # Pre-check: Reject dangerous SQL syntax characters immediately
    if any(char in expr_clean for char in [";", "--", "/*", "*/"]):
        raise ValueError("Expression contains invalid characters or SQL comments.")

    # Validate aggregation function
    valid_aggs = {"SUM", "AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX"}
    agg_upper = aggregation.strip().upper()
    if agg_upper not in valid_aggs:
        raise ValueError(f"Invalid aggregation '{aggregation}'. Allowed: {', '.join(sorted(valid_aggs))}")

    # Build allowed columns set
    col_set = set(allowed_columns)
    validator = SafeExpressionValidator(col_set)

    # If the expression is a direct column reference with spaces or special characters (e.g. `Total Sales`),
    # handle both clean identifiers and space-separated column names.
    # First check if the expression itself directly matches a column name (case-insensitive)
    col_match = next((c for c in allowed_columns if c.lower() == expr_clean.lower().strip("`")), None)
    if col_match:
        referenced_columns = [col_match]
        if agg_upper == "COUNT_DISTINCT":
            compiled_sql = f"COUNT(DISTINCT `{col_match}`)"
        else:
            compiled_sql = f"{agg_upper}(`{col_match}`)"
        return compiled_sql, referenced_columns

    # Parse with Python AST
    try:
        parsed = ast.parse(expr_clean, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e.msg}")

    # Run AST safety validation
    validator.visit(parsed)

    # Compile to SQL
    raw_sql = _ast_to_sql(parsed, validator.allowed_columns_map)

    # Wrap in aggregation
    if agg_upper == "COUNT_DISTINCT":
        if len(validator.referenced_columns) == 1:
            compiled_sql = f"COUNT(DISTINCT `{validator.referenced_columns[0]}`)"
        else:
            compiled_sql = f"COUNT(DISTINCT {raw_sql})"
    else:
        compiled_sql = f"{agg_upper}{raw_sql}"

    return compiled_sql, validator.referenced_columns
