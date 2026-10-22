"""The cloud database (Azure SQL): settings, sign-in, schema, loading and the one-off Azure setup.

No passwords or keys anywhere: every connection signs in with your Microsoft (Entra ID) account,
and the server refuses password logins. See tools/2_load_azure/database/README.md.
"""
