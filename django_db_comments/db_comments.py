from psycopg2 import sql

from django.apps import apps as global_apps
from django.db import DEFAULT_DB_ALIAS, router, connections, transaction
from django.conf import settings

# django engines support
# 'django.db.backends.postgresql'
# 'django.db.backends.postgresql_psycopg2'
# 'django.db.backends.mysql'
# 'django.db.backends.sqlite3'
# 'django.db.backends.oracle'
ALLOWED_ENGINES = [
    "django.db.backends.postgresql",
    "django.contrib.gis.db.backends.postgis",
    "django.db.backends.postgresql_psycopg2",
    "psqlextra.backend",
]

# http://initd.org/psycopg/docs/sql.html
# https://www.postgresql.org/docs/9.6/sql-comment.html
POSTGRES_COMMENT_SQL = sql.SQL("COMMENT ON COLUMN {}.{} IS %s")

POSTGRES_COMMENT_ON_TABLE_SQL = sql.SQL("COMMENT ON TABLE {} IS %s")


def get_comments_for_model(model):
    column_comments = {}

    for field in model._meta.fields:
        comment = []
        # Check if verbose name was not autogenerated, according to django code
        # https://github.com/django/django/blob/9681e96/django/db/models/fields/__init__.py#L724
        if field.verbose_name.lower() != field.name.lower().replace("_", " "):
            comment.append(
                str(field.verbose_name)
            )  # str() is workaround for Django.ugettext_lazy
        if field.help_text:
            comment.append(
                str(field.help_text)
            )  # str() is workaround for Django.ugettext_lazy
        if comment:
            column_comments[field.column] = " | ".join(comment)

    return column_comments


def add_comments_to_database(
    tables_comments, table_comment_dict, using=DEFAULT_DB_ALIAS
):
    with connections[using].cursor() as cursor:
        with transaction.atomic():
            for table, columns in tables_comments.items():
                query_for_tablecomment = POSTGRES_COMMENT_ON_TABLE_SQL.format(
                    sql.Identifier(table)
                )
                table_verbose_name = ""
                if table_comment_dict[table]:
                    table_verbose_name = table_comment_dict[table]
                cursor.execute(query_for_tablecomment, [table_verbose_name])

                for column, comment in columns.items():
                    query = POSTGRES_COMMENT_SQL.format(
                        sql.Identifier(table), sql.Identifier(column)
                    )
                    cursor.execute(query, [comment])


def copy_help_texts_to_database(
    app_config,
    verbosity=2,
    interactive=True,
    using=DEFAULT_DB_ALIAS,
    apps=global_apps,
    **kwargs
):
    """
    Create content types for models in the given app.
    """
    if not app_config.models_module:
        return

    if settings.DATABASES[using]["ENGINE"] not in ALLOWED_ENGINES:
        return

    app_label = app_config.label
    if not router.allow_migrate(using, app_label):
        return

    app_config = apps.get_app_config(app_label)
    app_models = app_config.get_models()

    tables_comments = {
        model._meta.db_table: get_comments_for_model(model) for model in app_models
    }
    teblecomments = {
        model._meta.db_table: model._meta.verbose_name.title()
        for model in app_config.get_models()
    }

    if not tables_comments:
        return

    add_comments_to_database(tables_comments, teblecomments, using)

    if verbosity >= 2:
        for table, columns in tables_comments.items():
            for column, comment in columns.items():
                print("Adding comment in %s for %s = '%s'" % (table, column, comment))
