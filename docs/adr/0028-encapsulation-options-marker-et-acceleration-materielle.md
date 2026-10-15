# Encapsulation des options Marker OCR, accélération matérielle et gouvernance des appels d'ingestion

**Statut :** accepté

Afin de permettre aux développeurs de piloter finement les performances et le comportement d'extraction de `marker-pdf` sans dégrader l'expérience utilisateur ni introduire de dépendances non supervisées vers des LLMs tiers, nous formalisons un contrat d'exécution typé (`MarkerOptions`), une gestion explicite de l'accélération matérielle (`TORCH_DEVICE`) et un mécanisme de surcharge par variables d'environnement.

## Le problème

Jusqu'alors, l'appel au moteur Marker OCR dans `DocumentParser._parse_pdf_with_marker` reposait sur une ligne de commande strictement figée en dur :
```python
cmd = [executable, str(file_path), "--output_dir", str(temp_dir), "--paginate_output"]
```
Ce fonctionnement présentait plusieurs limitations majeures :
1. **Absence de contrôle de portée** : Impossible en code ou en test de restreindre l'extraction à quelques pages d'un PDF volumineux (`--page_range`), obligeant à traiter 100 % du document.
2. **Impossibilité de moduler l'OCR** : Impossible de forcer la reconnaissance optique (`--force_ocr`) sur des scans dégradés, ni de désactiver l'OCR (`--disable_ocr`) pour une extraction vectorielle ultra-rapide.
3. **Opacité matérielle** : Le sous-processus `marker_single` héritait de l'environnement sans consigne de périphérique (`TORCH_DEVICE`). Sur Apple Silicon (macOS ARM64), cela pouvait entraîner des replis CPU inefficaces ; en environnement de test CI, l'absence de contrôle sur le GPU pouvait provoquer des fuites mémoire.
4. **Risque de dérive LLM interne** : Marker 1.8+ propose un drapeau `--use_llm` avec services distants (OpenAI, Gemini, Claude). Laisser un outil externe exécuter des requêtes réseau non supervisées violerait la traçabilité des coûts, des tokens et des clés d'API sanctuarisée par le moteur DAG d'AnkiForge.

## Options considérées

1. **Dialogue modal IHM de paramétrage utilisateur avant chaque import** :
   Rejeté. Alourdirait inutilement le parcours utilisateur pour une opération d'ingestion qui doit rester rapide et fluide. L'utilisateur final attend que Marker fonctionne au mieux automatiquement.
2. **Configuration globale mutable (Singleton / Registre)** :
   Rejeté. L'état global partagé introduit des effets de bord entre les tests et complique l'exécution concurrente ou les passes différentielles.
3. **Dataclass typée `MarkerOptions`, injection par argument optionnel, sanctuarisation anti-LLM et détection matérielle** :
   **Retenu**.

## Décisions et Règles d'Architecture

### 1. Dataclass de configuration `MarkerOptions`
Le module `src/ankiforge/services/parsing/marker_service.py` héberge la dataclass `MarkerOptions` encapsulant les paramètres d'extraction :
- **Champs principaux** :
  - `page_range: str | None = None` : restriction de pages (ex: `"0-10"`).
  - `force_ocr: bool = False` : force la reconnaissance complète.
  - `disable_ocr: bool = False` : mode rapide sans modèles de vision lourds.
  - `strip_existing_ocr: bool = False` : élimine le texte OCR préalable.
  - `disable_ocr_math: bool = False` : désactive la détection KaTeX.
  - `extract_images: bool = True` : extrait les figures vers le dossier médias.
  - `filter_blank_pages: bool = False` : filtre les pages vides.
  - `highres_image_dpi: int = 192` & `lowres_image_dpi: int = 96` : résolutions optiques.
  - `pdftext_workers: int = 1` : nombre de processus d'extraction textuelle.
  - `debug: bool = False` : active les logs et dumps détaillés de Marker.
  - `device: str | None = None` : périphérique d'exécution cible.
  - `extra_cli_args: list[str] = field(default_factory=list)` : trappe de fuite pour arguments CLI additionnels.
- **Paramètre sanctuarisé** : `--paginate_output` est **toujours** injecté dans la ligne de commande, car `ChunkingService._MARKER_PAGE_RE` en dépend pour la pagination des fragments.
- **Interdiction formelle de `--use_llm`** : Le contrat d'options n'expose aucun service LLM tiers pour Marker. L'enrichissement sémantique relève exclusivement des pipelines d'AnkiForge.

### 2. Accélération matérielle et périphérique cible
La méthode de génération CLI configure l'environnement du sous-processus :
- Si `device` est spécifié (ex: `"cpu"`, `"mps"`, `"cuda"`), la variable d'environnement `TORCH_DEVICE` est positionnée dans `env`.
- Si `device is None`, une détection déterministe applique :
  - `mps` si macOS ARM64 (Apple Silicon) avec Metal disponible.
  - `cuda` si plateforme avec GPU Nvidia compatible.
  - `cpu` par défaut ou en environnement headless / CI.

### 3. Surcharge de développement local (`ANKIFORGE_MARKER_*`)
Une fabrique `MarkerOptions.from_env()` (ou l'initialisation par défaut) prend en compte les variables d'environnement de commodité :
- `ANKIFORGE_MARKER_PAGE_RANGE` (ex: `"1-5"`)
- `ANKIFORGE_MARKER_DISABLE_OCR` (`"1"` / `"true"`)
- `ANKIFORGE_MARKER_FORCE_OCR` (`"1"` / `"true"`)
- `ANKIFORGE_MARKER_DEVICE` (`"cpu"`, `"mps"`)
Permet au développeur de lancer `ANKIFORGE_MARKER_PAGE_RANGE=1-3 uv run ankiforge --dev` pour tester instantanément un document sans toucher au code.

### 4. Injection par argument optionnel
- `DocumentParser.parse_document` et `_parse_pdf_with_marker` acceptent `marker_options: MarkerOptions | None = None`.
- `DocumentWorker` accepte `marker_options: MarkerOptions | None = None`.
- Si omis, `MarkerOptions()` (combinant valeurs saines de production et surcharges d'environnement) est instancié.

## Conséquences

- **Flexibilité de test** : Possibilité de tester unitairement des extractions partielles en quelques secondes sans saturer les ressources.
- **Performance optimale** : Exploitation native du GPU Apple Silicon (`mps`) ou Nvidia (`cuda`) sans ralentissement CPU inattendu.
- **Souveraineté des données et intégrité des coûts** : Zéro appel API non supervisé par Marker, préservant la gouvernance stricte des dépenses de tokens.
- **Rétrocompatibilité totale** : Les appels existants ne passant aucun argument `marker_options` conservent exactement le comportement actuel.
