---
name: q-migrations
description: This skill generates database migration files using Alembic based on changes to SQLAlchemy models in components/qlegal/impl_repository_postgres/models.py. It ONLY generates the migration file - never executes it. The human is responsible for reviewing and applying the migration manually.
---

# Q-Migrations

## Purpose

Generate database migration files using Alembic based on changes to SQLAlchemy models in `components/qlegal/impl_repository_postgres/models.py`.

## ⚠️ CRITICAL: Revision ID Length Limit

**Alembic revision IDs MUST NOT exceed 32 characters.**

PostgreSQL stores revision IDs in a `VARCHAR(32)` column. Exceeding this limit causes:
```
sqlalchemy.exc.DataError: (psycopg2.errors.StringDataRightTruncation)
value too long for type character varying(32)
```

### Correct vs Incorrect Examples

```python
# ❌ WRONG - 46 characters
revision: str = "0005_add_deleted_at_and_standardize_audit_fields"

# ✅ CORRECT - 19 characters
revision: str = "0005_add_deleted_at"
```

### Naming Formula

Keep the revision ID short: `NNNN_brief_desc` where:
- `NNNN`: 4-digit number (0001, 0002, ...)
- `brief_desc`: 2-3 words maximum in snake_case

**Maximum safe length**: `NNNN_` (5 chars) + 27 chars for description = 32 total

## When to Use

Use this skill when:
- You modified models in `components/qlegal/impl_repository_postgres/models.py`
- You need to add a new table to the database
- You need to modify an existing table structure
- You need to add or remove columns from existing tables
- You need to create or remove indexes

## What This Skill Does

1. Reads the current models in `components/qlegal/impl_repository_postgres/models.py`
2. Checks the current migration state with `alembic current` and `alembic history`
3. Identifies the next revision number
4. Executes `alembic revision --autogenerate` to create the migration file
5. **Verifies the revision ID is ≤ 32 characters**

## What This Skill Does NOT Do

- ❌ Apply migrations to the database
- ❌ Edit the generated migration file
- ❌ Run `alembic upgrade`

## Workflow

### Step 1: Read the Models File

Read [`components/qlegal/impl_repository_postgres/models.py`](components/qlegal/impl_repository_postgres/models.py).

### Step 2: Check Current Migration State

Run:
```bash
cd projects/db_migration
uv run alembic current
uv run alembic history
```

### Step 3: Generate the Migration

Run alembic revision with autogenerate:
```bash
cd projects/db_migration
uv run alembic revision --autogenerate -m "description" --rev-id NNNN_brief_desc
```

Where:
- `NNNN` is the next 4-digit number after the current revision
- `brief_desc` is a **SHORT** snake_case description (max 27 chars to stay under 32 total)

### Step 4: Verify Revision ID Length

**MANDATORY**: After generation, verify the revision ID in the file:
```bash
# Check revision ID length
grep "^revision:" projects/db_migration/alembic/versions/NNNN_*.py
```

If the revision ID exceeds 32 characters, edit it immediately:
```python
# Change from
revision: str = "0006_very_long_description_that_exceeds_limit"
# To
revision: str = "0006_short_desc"
```

### Step 5: Verify File Creation

Verify the migration file was created in:
```
projects/db_migration/alembic/versions/NNNN_brief_desc.py
```

## Files

- Models: [`components/qlegal/impl_repository_postgres/models.py`](components/qlegal/impl_repository_postgres/models.py)
- Migration project: `projects/db_migration/`
- Migrations: `projects/db_migration/alembic/versions/`

## Example: Adding a New Column

Suppose you add a new column `is_active` to the `RawFileTable`:

```python
# components/qlegal/impl_repository_postgres/models.py
class RawFileTable(Base):
    __tablename__ = "raw_documents"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    # ... existing columns ...
    is_active = Column(Boolean, default=True, nullable=False)  # NEW
```

Run the migration:
```bash
cd projects/db_migration
uv run alembic revision --autogenerate -m "add is_active" --rev-id 0006_add_is_active
```

Verify the revision ID:
```bash
grep "^revision:" projects/db_migration/alembic/versions/0006_add_is_active.py
# Should output: revision: str = "0006_add_is_active" (20 chars ✓)
```

## Example: Creating a New Table

```python
# components/qlegal/impl_repository_postgres/models.py
class NewTable(Base):
    __tablename__ = "new_table"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

```bash
cd projects/db_migration
uv run alembic revision --autogenerate -m "create new table" --rev-id 0007_create_new_table
```
