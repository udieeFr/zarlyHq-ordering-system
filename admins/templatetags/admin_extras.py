from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """Usage: {{ value|replace:"old,new" }} or {{ value|replace:"_: " }} (replaces first char with second)"""
    # Support both "old,new" and "old new" (space-separated single chars treated as replace first with second)
    if ':' in arg:
        old, new = arg.split(':', 1)
    elif ',' in arg:
        old, new = arg.split(',', 1)
    else:
        # Treat as replace first char with second char e.g. "_ " replaces _ with space
        if len(arg) == 2:
            old, new = arg[0], arg[1]
        else:
            return value
    return str(value).replace(old, new)
