"""Tests for the DDL parser."""

from __future__ import annotations

import pytest

from snowflake_architect.ddl_parser import parse_ddl


class TestBasicTableParsing:
    def test_simple_create_table(self):
        ddl = """
        CREATE TABLE my_table (
            id INT,
            name VARCHAR(100)
        );
        """
        result = parse_ddl(ddl, default_database="PROD", default_schema="PUBLIC")

        assert len(result.objects) == 1
        obj = result.objects[0]
        assert obj.database == "PROD"
        assert obj.schema == "PUBLIC"
        assert obj.name == "MY_TABLE"
        assert obj.object_type == "TABLE"

    def test_fully_qualified_name(self):
        ddl = "CREATE TABLE analytics.reporting.fact_orders (id INT);"
        result = parse_ddl(ddl)

        obj = result.objects[0]
        assert obj.database == "ANALYTICS"
        assert obj.schema == "REPORTING"
        assert obj.name == "FACT_ORDERS"

    def test_schema_qualified_name(self):
        ddl = "CREATE TABLE staging.raw_events (id INT);"
        result = parse_ddl(ddl, default_database="WAREHOUSE")

        obj = result.objects[0]
        assert obj.database == "WAREHOUSE"
        assert obj.schema == "STAGING"
        assert obj.name == "RAW_EVENTS"

    def test_create_or_replace(self):
        ddl = "CREATE OR REPLACE TABLE my_table (id INT);"
        result = parse_ddl(ddl)

        assert len(result.objects) == 1
        assert result.objects[0].name == "MY_TABLE"
        assert result.objects[0].object_type == "TABLE"

    def test_create_if_not_exists(self):
        ddl = "CREATE TABLE IF NOT EXISTS my_table (id INT);"
        result = parse_ddl(ddl)

        assert len(result.objects) == 1
        assert result.objects[0].name == "MY_TABLE"

    def test_transient_table(self):
        ddl = "CREATE TRANSIENT TABLE stg_data (id INT);"
        result = parse_ddl(ddl)

        assert result.objects[0].is_transient is True
        assert result.objects[0].object_type == "TABLE"

    def test_quoted_identifiers(self):
        ddl = 'CREATE TABLE "My Database"."My Schema"."My Table" (id INT);'
        result = parse_ddl(ddl)

        obj = result.objects[0]
        assert obj.database == "MY DATABASE"
        assert obj.schema == "MY SCHEMA"
        assert obj.name == "MY TABLE"


class TestViewParsing:
    def test_simple_view(self):
        ddl = "CREATE VIEW v_orders AS SELECT * FROM orders;"
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        assert len(result.objects) == 1
        obj = result.objects[0]
        assert obj.name == "V_ORDERS"
        assert obj.object_type == "VIEW"

    def test_secure_view(self):
        ddl = "CREATE SECURE VIEW v_secure AS SELECT * FROM orders;"
        result = parse_ddl(ddl)

        assert result.objects[0].object_type == "VIEW"

    def test_materialized_view(self):
        ddl = "CREATE MATERIALIZED VIEW mv_summary AS SELECT id FROM fact_sales;"
        result = parse_ddl(ddl)

        assert result.objects[0].object_type == "MATERIALIZED VIEW"

    def test_create_or_replace_view(self):
        ddl = "CREATE OR REPLACE VIEW v_report AS SELECT * FROM base_table;"
        result = parse_ddl(ddl)

        assert result.objects[0].object_type == "VIEW"
        assert result.objects[0].name == "V_REPORT"


class TestLineageExtraction:
    def test_view_references_source(self):
        ddl = """
        CREATE TABLE raw_orders (id INT);
        CREATE VIEW v_orders AS SELECT id FROM raw_orders;
        """
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        assert len(result.objects) == 2
        assert len(result.lineage_edges) == 1
        edge = result.lineage_edges[0]
        assert edge.source_name == "RAW_ORDERS"
        assert edge.target_name == "V_ORDERS"

    def test_view_with_join_references(self):
        ddl = """
        CREATE VIEW v_order_details AS
        SELECT o.id, c.name
        FROM orders o
        JOIN customers c ON o.customer_id = c.id;
        """
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        assert len(result.lineage_edges) == 2
        source_names = {e.source_name for e in result.lineage_edges}
        assert "ORDERS" in source_names
        assert "CUSTOMERS" in source_names

    def test_ctas_references(self):
        ddl = """
        CREATE TABLE summary AS
        SELECT category, SUM(amount)
        FROM transactions
        GROUP BY category;
        """
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        assert len(result.lineage_edges) == 1
        assert result.lineage_edges[0].source_name == "TRANSACTIONS"
        assert result.lineage_edges[0].target_name == "SUMMARY"

    def test_view_with_cte(self):
        ddl = """
        CREATE VIEW v_top_customers AS
        WITH ranked AS (
            SELECT customer_id, SUM(total) as total_spend
            FROM orders
            GROUP BY customer_id
        )
        SELECT r.customer_id, c.name
        FROM ranked r
        JOIN customers c ON r.customer_id = c.id;
        """
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        source_names = {e.source_name for e in result.lineage_edges}
        assert "ORDERS" in source_names
        assert "CUSTOMERS" in source_names

    def test_fully_qualified_references(self):
        ddl = """
        CREATE VIEW db1.public.v_combined AS
        SELECT a.id FROM db2.raw.source_table a;
        """
        result = parse_ddl(ddl)

        assert len(result.lineage_edges) == 1
        edge = result.lineage_edges[0]
        assert edge.source_database == "DB2"
        assert edge.source_schema == "RAW"
        assert edge.source_name == "SOURCE_TABLE"

    def test_no_lineage_for_plain_table(self):
        ddl = "CREATE TABLE plain_table (id INT, name VARCHAR);"
        result = parse_ddl(ddl)

        assert len(result.lineage_edges) == 0

    def test_no_self_reference(self):
        ddl = """
        CREATE VIEW v_data AS
        SELECT * FROM source_data;
        """
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        # Should not include v_data referencing itself
        for edge in result.lineage_edges:
            assert edge.source_name != "V_DATA"


class TestTableProperties:
    def test_cluster_by(self):
        ddl = """
        CREATE TABLE events (
            event_date DATE,
            user_id INT,
            event_type VARCHAR
        )
        CLUSTER BY (event_date, user_id);
        """
        result = parse_ddl(ddl)

        assert result.objects[0].clustering_key == "event_date, user_id"

    def test_retention_time(self):
        ddl = """
        CREATE TABLE tmp_data (id INT)
        DATA_RETENTION_TIME_IN_DAYS = 0;
        """
        result = parse_ddl(ddl)

        assert result.objects[0].retention_time == 0

    def test_comment(self):
        ddl = """
        CREATE TABLE documented_table (id INT)
        COMMENT = 'This is a staging table for raw event data';
        """
        result = parse_ddl(ddl)

        assert result.objects[0].comment == "This is a staging table for raw event data"


class TestMultipleStatements:
    def test_multiple_creates(self):
        ddl = """
        CREATE TABLE raw_events (id INT, data VARIANT);
        CREATE TABLE dim_users (user_id INT, name VARCHAR);
        CREATE VIEW v_events AS SELECT id FROM raw_events;
        CREATE MATERIALIZED VIEW mv_user_events AS
            SELECT u.name, e.id
            FROM raw_events e
            JOIN dim_users u ON e.id = u.user_id;
        """
        result = parse_ddl(ddl, default_database="ANALYTICS", default_schema="PUBLIC")

        assert len(result.objects) == 4
        types = {o.name: o.object_type for o in result.objects}
        assert types["RAW_EVENTS"] == "TABLE"
        assert types["DIM_USERS"] == "TABLE"
        assert types["V_EVENTS"] == "VIEW"
        assert types["MV_USER_EVENTS"] == "MATERIALIZED VIEW"

        # v_events depends on raw_events
        # mv_user_events depends on raw_events and dim_users
        assert len(result.lineage_edges) == 3

    def test_no_trailing_semicolon(self):
        ddl = "CREATE TABLE t1 (id INT)\nCREATE TABLE t2 (id INT)"
        # Without semicolons this is actually one statement - but the regex should
        # still find the first CREATE TABLE. The second will be part of the same statement.
        result = parse_ddl(ddl)
        assert len(result.objects) >= 1

    def test_mixed_case(self):
        ddl = """
        create table lowercase_table (id int);
        CREATE TABLE UPPERCASE_TABLE (ID INT);
        Create Or Replace Table MixedCase_Table (Id Int);
        """
        result = parse_ddl(ddl)

        assert len(result.objects) == 3
        names = {o.name for o in result.objects}
        assert "LOWERCASE_TABLE" in names
        assert "UPPERCASE_TABLE" in names
        assert "MIXEDCASE_TABLE" in names


class TestEdgeCases:
    def test_empty_input(self):
        result = parse_ddl("")
        assert len(result.objects) == 0
        assert len(result.lineage_edges) == 0

    def test_non_create_statements(self):
        ddl = """
        INSERT INTO my_table VALUES (1, 'a');
        DROP TABLE old_table;
        ALTER TABLE my_table ADD COLUMN new_col INT;
        """
        result = parse_ddl(ddl)
        assert len(result.objects) == 0

    def test_comments_in_ddl(self):
        ddl = """
        -- This is a comment
        CREATE TABLE my_table (
            id INT -- primary key
        );
        """
        result = parse_ddl(ddl)
        assert len(result.objects) == 1
        assert result.objects[0].name == "MY_TABLE"

    def test_dynamic_table(self):
        ddl = """
        CREATE DYNAMIC TABLE product_agg
            TARGET_LAG = '1 hour'
            WAREHOUSE = compute_wh
        AS
        SELECT product_id, SUM(quantity) as total_qty
        FROM raw_sales
        GROUP BY product_id;
        """
        result = parse_ddl(ddl, default_database="DB", default_schema="PUBLIC")

        assert len(result.objects) == 1
        assert result.objects[0].name == "PRODUCT_AGG"
        assert result.objects[0].object_type == "TABLE"
        assert len(result.lineage_edges) == 1
        assert result.lineage_edges[0].source_name == "RAW_SALES"


class TestIntegrationWithAnalyzer:
    """Verify DDL-parsed metadata works with the full analysis pipeline."""

    def test_ddl_through_analyzer(self):
        from snowflake_architect.analyzer import ArchitectureAnalyzer
        from snowflake_architect.recommender import generate_recommendations

        ddl = """
        CREATE TABLE raw_orders (id INT, customer_id INT, amount DECIMAL);
        CREATE TABLE raw_customers (id INT, name VARCHAR, email VARCHAR);
        CREATE TABLE stg_orders (id INT, customer_id INT, amount DECIMAL);

        CREATE VIEW v_order_summary AS
        SELECT o.id, c.name, o.amount
        FROM stg_orders o
        JOIN raw_customers c ON o.customer_id = c.id;

        CREATE VIEW v_dashboard AS
        SELECT * FROM v_order_summary;
        """
        metadata = parse_ddl(ddl, default_database="PROD", default_schema="PUBLIC")

        analyzer = ArchitectureAnalyzer(metadata)
        analysis = analyzer.analyze()

        assert analysis.object_count == 5
        assert analysis.edge_count > 0

        report = generate_recommendations(analysis, goals=["simplify"])
        assert report is not None
        assert len(report.goals) > 0
