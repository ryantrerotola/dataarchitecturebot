# Snowflake Architecture Analyzer

Analyzes your Snowflake data architecture and recommends improvements based on your goals (reduce compute, reduce storage, simplify, etc.). Works two ways:

1. **Live connection** — connects to your Snowflake account to extract metadata, lineage, and usage stats
2. **DDL mode** — paste or point to a `.sql` file with your DDL (no Snowflake connection needed)

## What it detects

- **Circular dependencies** — data flowing in loops between objects
- **Stale data** — tables not modified in 90+ days still consuming storage
- **Unused objects** — tables/views with no read queries
- **Write-only tables** — data being loaded but never consumed
- **Deep lineage chains** — excessively long transformation pipelines (8+ hops)
- **High fan-out** — single objects feeding 10+ downstream dependents
- **Potential duplicates** — tables with identical row counts and sizes
- **Large unclustered tables** — tables over 1 GB missing clustering keys
- **Transient candidates** — staging/temp tables with unnecessary Time Travel retention
- **Single-source bottlenecks** — critical objects with no redundancy
- **Schema sprawl** — databases with 50+ schemas

## Requirements

- Python 3.10+
- **For live connection mode:** A Snowflake account with access to `SNOWFLAKE.ACCOUNT_USAGE`
- **For DDL mode:** Just your DDL statements in a file or on the clipboard — no Snowflake account needed

## Installation

```bash
pip install -e .
```

## Configuration

### Option 1: Environment variables

```bash
export SNOWFLAKE_ACCOUNT="your-account.us-east-1"
export SNOWFLAKE_USER="your_user"
export SNOWFLAKE_PASSWORD="your_password"
export SNOWFLAKE_ROLE="ACCOUNTADMIN"
export SNOWFLAKE_WAREHOUSE="COMPUTE_WH"
```

### Option 2: Config file

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your connection details
```

### Option 3: Both

Environment variables override config file values. Use the config file for non-sensitive settings and env vars for credentials.

## Usage

### Analyze from DDL (no Snowflake connection needed)

The fastest way to get started — just point to a SQL file with your CREATE TABLE/VIEW statements:

```bash
# From a DDL file
snowflake-architect analyze --ddl-file my_schema.sql -g simplify

# With a specific default database/schema for unqualified names
snowflake-architect analyze --ddl-file my_schema.sql \
  --default-database PROD \
  --default-schema ANALYTICS \
  -g reduce_compute

# Paste DDL interactively from stdin
snowflake-architect analyze --ddl -g reduce_storage
# Then paste your DDL and press Ctrl+D when done

# Pipe DDL from another command
cat schema.sql | snowflake-architect analyze --ddl -g simplify
```

The DDL parser extracts:
- **Objects** — tables, views, materialized views, dynamic tables, transient tables
- **Lineage** — which objects depend on which (from view definitions and CTAS)
- **Properties** — clustering keys, retention settings, transient flags, comments

### Analyze from live Snowflake connection

```bash
# With env vars
snowflake-architect analyze

# With config file
snowflake-architect -c config.yaml analyze

# With specific goals
snowflake-architect analyze -g reduce_compute -g reduce_storage

# With all options
snowflake-architect -c config.yaml analyze \
  -g simplify \
  -g reduce_compute \
  --stale-days 60 \
  --low-usage-days 14 \
  -o ./my-reports
```

The live connection additionally provides query usage stats, warehouse costs, and stale/unused object detection (which DDL mode can't provide since there's no runtime data).

### List available goals

```bash
snowflake-architect goals
```

### Test connection

```bash
snowflake-architect test-connection
```

## Goals

| Goal | Description |
|------|-------------|
| `reduce_compute` | Reduce credit consumption and compute costs |
| `reduce_storage` | Reduce storage costs by removing or archiving unused data |
| `simplify` | Simplify the data architecture and reduce complexity |
| `improve_reliability` | Improve pipeline reliability and reduce failure risk |
| `improve_performance` | Improve query and pipeline performance |
| `governance` | Improve data governance, discovery, and compliance |

Goals control which findings are prioritized in the report. You can specify multiple goals and they'll be weighted together. If no goals are specified, all findings are shown with equal priority.

## Output

The tool generates a Markdown report in the output directory containing:

- Executive summary with key metrics
- Mermaid lineage diagram of your data flow
- Prioritized recommendations based on your goals
- Detailed findings with affected objects and remediation steps
- Object inventory by type and database

## Required Snowflake Permissions (live connection mode only)

The tool queries these Snowflake system views:

- `<DATABASE>.INFORMATION_SCHEMA.TABLES` — object metadata
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` — lineage and usage data
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` — query statistics
- `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` — warehouse costs

Grant access with:

```sql
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE your_role;
```
