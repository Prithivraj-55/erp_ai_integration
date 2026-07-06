"""SQL validation + permission enforcement for AI-generated queries.

Defense in depth: the read-only DB user already prevents writes, but this
module additionally guarantees that only a single plain SELECT touching
permitted tables is ever executed, with an enforced LIMIT.

Fail-closed policy: anything this parser cannot positively identify is
rejected.
"""

import re

import sqlparse
from sqlparse.sql import Function, Identifier, IdentifierList, Parenthesis
from sqlparse.tokens import CTE, DML, Keyword, Punctuation

from erp_ai_integration.permissions.access import PermissionDenied, check_table_allowed

__all__ = ["GuardError", "PermissionDenied", "guard_sql", "extract_tables"]


class GuardError(Exception):
	"""Query rejected for a structural/safety reason (not permissions)."""


FORBIDDEN_PATTERNS = [
	re.compile(p, re.IGNORECASE)
	for p in (
		r"\bINTO\s+(OUTFILE|DUMPFILE)\b",
		r"\bLOAD_FILE\s*\(",
		r"\bSLEEP\s*\(",
		r"\bBENCHMARK\s*\(",
		r"\bGET_LOCK\s*\(",
		r"\bRELEASE_LOCK\s*\(",
		r"\bMASTER_POS_WAIT\s*\(",
		r"\bINFORMATION_SCHEMA\b",
		r"\bPERFORMANCE_SCHEMA\b",
		r"\bFOR\s+UPDATE\b",
		r"\bLOCK\s+IN\s+SHARE\s+MODE\b",
		r"\bINTO\s+@",  # SELECT ... INTO @var
	)
]

TABLE_KEYWORD = re.compile(
	r"^(FROM|JOIN|INNER\s+JOIN|CROSS\s+JOIN|STRAIGHT_JOIN"
	r"|LEFT(\s+OUTER)?\s+JOIN|RIGHT(\s+OUTER)?\s+JOIN|FULL(\s+OUTER)?\s+JOIN)$",
	re.IGNORECASE,
)

LIMIT_AT_END = re.compile(
	r"\bLIMIT\s+(\d+)(\s*,\s*\d+|\s+OFFSET\s+\d+)?\s*$", re.IGNORECASE
)


def guard_sql(sql: str, user: str, row_limit: int = 100) -> str:
	"""Validate an AI-generated query for `user` and return the safe SQL to
	execute (with LIMIT enforced).

	Raises GuardError for structural violations and PermissionDenied(doctype)
	when a referenced table is not permitted for the user.
	"""
	if not sql or not sql.strip():
		raise GuardError("Empty query")

	# MySQL executes /*! ... */ "conditional comments" — reject outright rather
	# than trusting the comment stripper
	if "/*!" in sql:
		raise GuardError("Executable comments (/*! ... */) are not allowed")

	# strip comments
	cleaned = sqlparse.format(sql, strip_comments=True).strip()
	cleaned = cleaned.rstrip(";").strip()
	if not cleaned:
		raise GuardError("Empty query")
	if ";" in cleaned:
		raise GuardError("Multiple statements are not allowed")

	statements = [s for s in sqlparse.parse(cleaned) if s.token_first(skip_cm=True)]
	if len(statements) != 1:
		raise GuardError("Exactly one statement is allowed")
	statement = statements[0]

	first = statement.token_first(skip_cm=True)
	if first.ttype is CTE or (first.ttype is Keyword and first.normalized == "WITH"):
		raise GuardError("WITH/CTE queries are not supported — rewrite using a subquery")
	if statement.get_type() != "SELECT":
		raise GuardError("Only SELECT statements are allowed")

	for pattern in FORBIDDEN_PATTERNS:
		if pattern.search(cleaned):
			raise GuardError(f"Forbidden expression in query: {pattern.pattern}")

	tables = extract_tables(statement)
	for table in sorted(tables):
		check_table_allowed(user, table)

	return _enforce_limit(cleaned, row_limit)


def _enforce_limit(sql: str, row_limit: int) -> str:
	match = LIMIT_AT_END.search(sql)
	if not match:
		return f"{sql} LIMIT {row_limit}"
	count = int(match.group(1))
	# for "LIMIT offset, count" the count is the second number
	if match.group(2) and "," in match.group(2):
		count = int(match.group(2).replace(",", "").strip())
	if count > row_limit:
		# replace the whole LIMIT clause with a simple capped one
		return sql[: match.start()].rstrip() + f" LIMIT {row_limit}"
	return sql


def extract_tables(statement) -> set[str]:
	"""All real table names referenced in FROM/JOIN clauses, including
	subqueries anywhere in the statement. Fail-closed: unidentifiable
	constructs raise GuardError."""
	tables: set[str] = set()
	_walk(statement, tables)
	return tables


def _walk(token_list, tables: set[str]):
	expecting_table = False
	for token in token_list.tokens:
		if token.is_whitespace:
			continue

		if token.ttype in (Keyword, DML):
			if TABLE_KEYWORD.match(token.normalized):
				expecting_table = True
			else:
				expecting_table = False
			continue

		if expecting_table:
			_consume_table_token(token, tables)
			# a comma right after means another table follows (old-style joins)
			if not (token.ttype is Punctuation and token.value == ","):
				expecting_table = False
			continue

		if token.ttype is Punctuation:
			continue

		# not in table position: still recurse for subqueries (WHERE x IN (SELECT ...))
		if token.is_group:
			_walk(token, tables)


def _consume_table_token(token, tables: set[str]):
	if isinstance(token, IdentifierList):
		for ident in token.get_identifiers():
			_consume_table_token(ident, tables)
		return

	if isinstance(token, Parenthesis):
		# derived table: ( SELECT ... ) — recurse
		_walk(token, tables)
		return

	if isinstance(token, Function):
		raise GuardError("Table functions are not allowed in FROM clause")

	if isinstance(token, Identifier):
		# aliased subquery: identifier wrapping a parenthesis
		inner = token.token_first(skip_cm=True)
		if isinstance(inner, Parenthesis):
			_walk(inner, tables)
			return
		if isinstance(inner, Function):
			raise GuardError("Table functions are not allowed in FROM clause")
		if token.get_parent_name():
			raise GuardError(
				f"Schema-qualified table '{token.get_parent_name()}.{token.get_real_name()}' is not allowed"
			)
		name = token.get_real_name()
		if not name:
			raise GuardError("Could not identify table name in FROM/JOIN clause")
		tables.add(name)
		return

	# bare name token (sqlparse sometimes leaves single names ungrouped)
	if token.ttype and token.ttype in Keyword:
		raise GuardError(f"Unexpected keyword '{token.value}' in table position")
	value = token.value.strip().strip("`")
	if value and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ]*", value):
		tables.add(value)
		return

	raise GuardError("Could not identify table in FROM/JOIN clause")
