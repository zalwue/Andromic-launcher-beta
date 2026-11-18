"""Evaluation of Mojang version-manifest rules and argument templates."""
from .system import ARCH, OS


def rules_ok(rules, features=None) -> bool:
    if not rules:
        return True
    features = features or {}
    allowed = False
    for rule in rules:
        match = True
        os_rule = rule.get("os")
        if os_rule:
            if "name" in os_rule and os_rule["name"] != OS:
                match = False
            if "arch" in os_rule and os_rule["arch"] != ARCH:
                match = False
        feature_rule = rule.get("features")
        if feature_rule:
            for key, value in feature_rule.items():
                if bool(features.get(key, False)) != bool(value):
                    match = False
        if match:
            allowed = rule.get("action") == "allow"
    return allowed


def expand_args(args, features, mapping) -> list:
    out = []
    for arg in args:
        if isinstance(arg, str):
            values = [arg]
        else:
            if not rules_ok(arg.get("rules"), features):
                continue
            value = arg["value"]
            values = [value] if isinstance(value, str) else value
        for text in values:
            for key, replacement in mapping.items():
                text = text.replace("${%s}" % key, replacement)
            out.append(text)
    return out
