# -*- coding: utf-8 -*-
"""
Pipeline factory — creates the workspace mod pipeline and provides
a FastAPI dependency for injecting it into routes.

The pipeline is created once at startup. Each request gets a fresh
PipelineContext carrying the DB session and auth info.
"""

from openagents.core.onm_pipeline import Pipeline

from app.mods.auth import AuthMod
from app.mods.workspace_mod import WorkspaceMod
from app.mods.persistence import PersistenceMod


# Singleton pipeline — created once at startup, reused across requests:
# auth → workspace → persistence.
pipeline = Pipeline(mods=[
    AuthMod(),           # guard,     priority 0
    WorkspaceMod(),      # transform, priority 50
    PersistenceMod(),    # observe,   priority 90
])
