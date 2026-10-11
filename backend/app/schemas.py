def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

def string(limit=4000):
    return {"type": "string", "minLength": 1, "maxLength": limit}

def array(items, minimum=0, maximum=100):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}

EVIDENCE = array(obj({"quote": string(600), "page": {"type": "integer", "minimum": 1}}), 1, 6)
