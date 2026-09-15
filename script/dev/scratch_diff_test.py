import difflib

a = "Hello\nWorld\nThis is a test".splitlines(keepends=True)
b = "Hello\nUniverse\nThis is a test\nWith more lines".splitlines(keepends=True)

for line in difflib.unified_diff(a, b):
    print(repr(line))
