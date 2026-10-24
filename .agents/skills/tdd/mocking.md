# Lignes Directrices de Mocking dans AnkiForge 🎭

Dans AnkiForge, le mocking obéit à des règles d'ingénierie strictes destinées à garantir des tests déterministes, ultra-rapides (< 15s pour la suite fast) et sans fuite mémoire ni coût externe.

---

## 1. Où Poser les Mocks : Les Frontières Système Uniquement

Dans AnkiForge, on mocke exclusivement aux **frontières externes réelles** que l'application ne contrôle pas :

### A. Fournisseurs d'IA & Embeddings (Règle Absolue non négociable)
- **Zéro appel réel en test** : interdiction absolue d'appeler les API distantes (OpenAI, Gemini, Anthropic) ou locales (démon Ollama).
- **Mocker au niveau de `flexible_service.create_provider()` ou `LLMProvider`** avec des réponses déterministes (JSON typé ou texte attendu).

```python
# Exemple canonique : mock déterministe d'un appel d'extraction de cartes
from unittest.mock import MagicMock, patch

def test_extraction_pipeline_with_mocked_llm():
    mock_provider = MagicMock()
    mock_provider.generate_text.return_value = '{"cards": [{"front": "Q", "back": "A"}]}'
    
    with patch("ankiforge.services.ai.flexible_service.create_provider", return_value=mock_provider):
        result = run_extraction_step(text="Source document")
        assert len(result.cards) == 1
        assert result.cards[0].front == "Q"
```

### B. Outils Multimédia & Réseau Externes
- **Marker OCR / PyTorch** : mocker la conversion PDF vers Markdown dans les tests rapides.
- **Edge-TTS / Synthèse Vocale** : mocker la génération de fichiers audio `.mp3`.
- **Téléchargement Web / YouTube** : mocker les requêtes HTTP via `responses` ou `unittest.mock.patch`.

### C. Workers Asynchrones & Threads Qt
- Pour tester le résultat d'un worker sans bloquer ni subir l'asynchronisme en test unitaire :
  - Soit exécuter la méthode `run()` directement de manière synchrone.
  - Soit utiliser `qtbot.waitSignal(worker.finished, timeout=2000)` pour laisser la boucle d'événements Qt se synchroniser proprement.

---

## 2. Ce qu'il est STRICTEMENT INTERDIT de Mocker

1. **La base de données Peewee ORM** :
   - ⛔ **Ne jamais mocker `Model.save()`, `Model.select()` ou `Model.create()`**.
   - ✅ **Utiliser la fixture `mock_db`** qui fournit une base SQLite en mémoire partagée (`file:memdb_test_<worker>?mode=memory&cache=shared`). Les contraintes de clés étrangères, unicité et clauses CASCADE y sont réellement exécutées.
2. **Vos propres classes et algorithmes internes** :
   - Ne pas mocker `ChunkingService`, `LinterService` ou `CoverageAlignmentService` lorsqu'on teste un service qui les emploie. Laissez le code métier s'exécuter.
3. **Le système de fichiers pour les fichiers temporaires** :
   - Préférer la fixture standard `tmp_path` de pytest plutôt que de mocker `open()` ou `Path.write_text()`.

---

## 3. Conception pour la Testabilité (Injection de Dépendances)

Favoriser l'injection de dépendances pour faciliter les tests :

```python
# FACILE À TESTER : le fournisseur ou le client est injecté
class CardGeneratorService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or create_default_provider()

    def generate(self, text: str) -> list[Card]:
        raw_json = self.provider.generate_text(text)
        return self._parse_cards(raw_json)


# En test :
def test_generator():
    fake_provider = FakeLLMProvider(canned_response="...")
    service = CardGeneratorService(provider=fake_provider)
    cards = service.generate("sample")
    assert len(cards) > 0
```
