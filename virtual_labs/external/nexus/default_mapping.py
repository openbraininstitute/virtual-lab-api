DEFAULT_MAPPING = {
    "dynamic": True,
    "properties": {
        "@id": {"type": "keyword"},
        "@type": {"type": "keyword"},
        "annotation": {
            "properties": {
                "hasBody": {
                    "properties": {
                        "label": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        },
                        "prefLabel": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        },
                    },
                    "type": "nested",
                }
            },
            "type": "object",
        },
        "atlasRelease": {
            "properties": {
                "@id": {"fields": {"keyword": {"type": "keyword"}}, "type": "keyword"}
            }
        },
        "brainLocation": {
            "properties": {
                "atlasSpatialReferenceSystem": {
                    "properties": {
                        "@id": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "keyword",
                        }
                    },
                    "type": "object",
                },
                "brainRegion": {
                    "properties": {
                        "@id": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "keyword",
                        },
                        "label": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        },
                    },
                    "type": "nested",
                },
                "coordinatesInBrainAtlas": {
                    "properties": {
                        "valueX": {
                            "properties": {
                                "@type": {"type": "keyword"},
                                "@value": {
                                    "fields": {"keyword": {"type": "keyword"}},
                                    "type": "float",
                                },
                            },
                            "type": "object",
                        },
                        "valueY": {
                            "properties": {
                                "@type": {"type": "keyword"},
                                "@value": {
                                    "fields": {"keyword": {"type": "keyword"}},
                                    "type": "float",
                                },
                            },
                            "type": "object",
                        },
                        "valueZ": {
                            "properties": {
                                "@type": {"type": "keyword"},
                                "@value": {
                                    "fields": {"keyword": {"type": "keyword"}},
                                    "type": "float",
                                },
                            },
                            "type": "object",
                        },
                    },
                    "type": "object",
                },
                "layer": {
                    "properties": {
                        "label": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        }
                    },
                    "type": "object",
                },
            },
            "type": "nested",
        },
        "contribution": {
            "properties": {
                "agent": {
                    "properties": {
                        "@id": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "keyword",
                        },
                        "@type": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        },
                    },
                    "type": "nested",
                }
            },
            "type": "nested",
        },
        "derivation": {
            "properties": {
                "entity": {
                    "properties": {
                        "@type": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        },
                        "name": {
                            "fields": {"keyword": {"type": "keyword"}},
                            "type": "text",
                        },
                    },
                    "type": "nested",
                }
            },
            "type": "nested",
        },
        "description": {"fields": {"keyword": {"type": "keyword"}}, "type": "text"},
        "dimension": {"type": "nested"},
        "distribution": {
            "properties": {
                "contentSize": {"type": "nested"},
                "contentUrl": {"type": "keyword"},
                "digest": {
                    "properties": {"value": {"type": "keyword"}},
                    "type": "nested",
                },
                "encodingFormat": {"type": "keyword"},
            },
            "type": "nested",
        },
        "generation": {"type": "nested"},
        "isRegisteredIn": {"properties": {"@id": {"type": "keyword"}}},
        "license": {
            "properties": {
                "label": {"fields": {"keyword": {"type": "keyword"}}, "type": "text"}
            },
            "type": "object",
        },
        "name": {"fields": {"keyword": {"type": "keyword"}}, "type": "text"},
        "objectOfStudy": {
            "properties": {
                "label": {"fields": {"keyword": {"type": "keyword"}}, "type": "text"}
            },
            "type": "object",
        },
        "parcellationOntology": {"properties": {"@id": {"type": "keyword"}}},
        "parcellationVolume": {"properties": {"@id": {"type": "keyword"}}},
        "recordMeasure": {"type": "nested"},
        "series": {
            "properties": {
                "statistic": {
                    "fields": {"keyword": {"type": "keyword"}},
                    "type": "text",
                },
                "unitCode": {
                    "fields": {"keyword": {"type": "keyword"}},
                    "type": "text",
                },
            },
            "type": "nested",
        },
        "spatialReferenceSystem": {
            "properties": {
                "@id": {"fields": {"keyword": {"type": "keyword"}}, "type": "keyword"}
            }
        },
        "subject": {"type": "object"},
        "_createdAt": {"type": "date"},
        "_createdBy": {"type": "keyword"},
        "_updatedAt": {"type": "date"},
        "_updatedBy": {"type": "keyword"},
    },
}
