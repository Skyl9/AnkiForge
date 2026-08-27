import tiktoken


def count_tokens(text, model="gpt-4"):
    # On récupère l'encodage spécifique au modèle
    encoding = tiktoken.encoding_for_model(model)
    tokens = encoding.encode(text)
    return len(tokens)


# Test
with open("llm_context.txt", "r") as f:
    content = f.read()
    result = count_tokens(content)


print(f"Nombre de tokens estimé : {result}")
