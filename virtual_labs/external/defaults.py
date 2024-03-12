from typing import List

AGGREGATE_SPARQL_VIEW = "AggregateSparqlView"
AGGREGATE_ELASTIC_SEARCH_VIEW = "AggregateElasticSearchView"
PROJECTS_TO_AGGREGATE = ["bbp/atlas"]
ES_RESOURCE_TYPE: List[str] = [
    "http://www.w3.org/ns/prov#Entity",
    "http://schema.org/Dataset",
    "http://www.w3.org/ns/prov#Activity",
    "http://www.w3.org/ns/prov#Agent",
]

ES_VIEW_ID = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset"
SP_VIEW_ID = "https://bluebrain.github.io/nexus/vocabulary/defaultSparqlIndex"
AG_ES_VIEW_ID = "https://bbp.epfl.ch/neurosciencegraph/data/views/aggreg-es/dataset"
AG_SP_VIEW_ID = "https://bbp.epfl.ch/neurosciencegraph/data/views/aggreg-sp/dataset"

ES_VIEWS = [
    {"_project": f"projects/{pr}", "@id": ES_VIEW_ID} for pr in PROJECTS_TO_AGGREGATE
]
SP_VIEWS = [
    {"_project": f"projects/{pr}", "@id": SP_VIEW_ID} for pr in PROJECTS_TO_AGGREGATE
]
