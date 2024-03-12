from enum import EnumType


class NexusError(Exception):
    message: str
    type: str

    def __init__(self, message: str, type: str) -> None:
        self.message = message
        self.type = type
        super().__init__(self.message)


class NexusErrorValue(EnumType):
    CREATE_PROJECT = "NEXUS_CREATE_PROJECT"
    CREATE_PROJECT_PERMISSION = "NEXUS_CREATE_PROJECT_PERMISSION"
    CREATE_RESOURCE = "NEXUS_CREATE_RESOURCE"
    CREATE_RESOLVER = "NEXUS_CREATE_RESOLVER"
    CREATE_ES_VIEW = "NEXUS_CREATE_ES_VIEW"
    CREATE_ES_AGG_VIEW = "NEXUS_CREATE_ES_AGG_VIEW"
    CREATE_SP_AGG_VIEW = "NEXUS_CREATE_SP_AGG_VIEW"
    FETCH_RESOURCE = "NEXUS_FETCH_RESOURCE"
