with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/maquette/concept_ide/index.html", "r") as f:
    content = f.read()

# Define replacement for Dashboard
dashboard_start = content.find("<!-- VUE : DASHBOARD -->")
forge_start = content.find("<!-- VUE : FORGE -->")

dashboard_content = """<!-- VUE : DASHBOARD -->
                        <div id="view-dashboard" class="view active">
                            <div class="split-view flex-1" style="gap: 12px; height: 100%;">
                                <!-- Left / Main Panel -->
                                <div class="ide-panel flex-1 flex-col">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-dash-home"><i class="ph ph-house"></i> Accueil</button>
                                        </div>
                                    </div>
                                    <div class="ide-panel-content p-0">
                                        <div id="tab-dash-home" class="sub-pane active flex-col h-full" style="padding: 24px; overflow-y: auto;">
                                            <div class="dashboard-hero-premium" style="margin-bottom: 24px;">
                                                <div class="hero-bg-glow"></div>
                                                <div class="hero-content">
                                                    <div class="logo-triangles mb-20">
                                                        <i class="ph ph-stack"></i>
                                                    </div>
                                                    <h1>Bienvenue dans <span>ankiforge_obsidian</span></h1>
                                                    <p class="muted mt-10">Le générateur de cartes intelligent et votre assistant d'apprentissage personnel.</p>
                                                </div>
                                            </div>

                                            <h3 class="mb-10"><i class="ph ph-lightning"></i> Actions Rapides</h3>
                                            <div class="grid-3" style="gap: 15px;">
                                                <button class="dashboard-btn-premium" onclick="document.querySelector('[data-view=\\'forge\\']').click()">
                                                    <div class="btn-icon-wrapper" style="background: rgba(59, 130, 246, 0.1); color: #3b82f6;">
                                                        <i class="ph ph-hammer"></i>
                                                    </div>
                                                    <div class="btn-text">
                                                        <span class="title">Forger des cartes</span>
                                                        <span class="desc">Depuis un document</span>
                                                    </div>
                                                </button>
                                                <button class="dashboard-btn-premium" onclick="document.querySelector('[data-view=\\'library\\']').click()">
                                                    <div class="btn-icon-wrapper" style="background: rgba(16, 185, 129, 0.1); color: #10b981;">
                                                        <i class="ph ph-books"></i>
                                                    </div>
                                                    <div class="btn-text">
                                                        <span class="title">Bibliothèque</span>
                                                        <span class="desc">Naviguer les paquets</span>
                                                    </div>
                                                </button>
                                                <button class="dashboard-btn-premium" onclick="document.querySelector('[data-view=\\'ai-studio\\']').click()">
                                                    <div class="btn-icon-wrapper" style="background: rgba(139, 92, 246, 0.1); color: #8b5cf6;">
                                                        <i class="ph ph-robot"></i>
                                                    </div>
                                                    <div class="btn-text">
                                                        <span class="title">Consulter l'IA</span>
                                                        <span class="desc">Configurer les agents</span>
                                                    </div>
                                                </button>
                                            </div>

                                            <div class="dashboard-dropzone mt-20 flex-grow" style="display: flex; flex-direction: column; justify-content: center; align-items: center; border: 2px dashed var(--border-color); border-radius: var(--radius-md); padding: 30px; text-align: center; background: var(--bg-secondary); transition: all 0.2s; min-height: 200px;">
                                                <i class="ph ph-upload-simple" style="font-size: 2.5rem; margin-bottom: 10px; color: var(--accent-primary);"></i>
                                                <h4>Glissez un PDF ou Document ici</h4>
                                                <p class="muted small">L'analyse sémantique et la génération démarreront automatiquement.</p>
                                                <button class="btn btn-secondary mt-15"><i class="ph ph-folder-open"></i> Parcourir les fichiers</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- Right Sidebar Panel -->
                                <div class="flex-col" style="gap: 12px; width: 320px;">
                                    <div class="ide-panel">
                                        <div class="ide-tabs">
                                            <div class="ide-tabs-list">
                                                <button class="ide-tab active" data-target="tab-dash-stats"><i class="ph ph-chart-line-up"></i> Statistiques</button>
                                            </div>
                                        </div>
                                        <div class="ide-panel-content">
                                            <div id="tab-dash-stats" class="sub-pane active flex-col h-full">
                                                <div class="stats-grid">
                                                    <div class="stat-item">
                                                        <span class="stat-val">1,245</span>
                                                        <span class="stat-lbl">Cartes Forgées</span>
                                                    </div>
                                                    <div class="stat-item">
                                                        <span class="stat-val text-green">98%</span>
                                                        <span class="stat-lbl">Taux Succès IA</span>
                                                    </div>
                                                    <div class="stat-item">
                                                        <span class="stat-val">14</span>
                                                        <span class="stat-lbl">Docs Analysés</span>
                                                    </div>
                                                    <div class="stat-item">
                                                        <span class="stat-val text-purple">3.5</span>
                                                        <span class="stat-lbl">Modèle par défaut</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="ide-panel flex-1">
                                        <div class="ide-tabs">
                                            <div class="ide-tabs-list">
                                                <button class="ide-tab active" data-target="tab-dash-activity"><i class="ph ph-clock-counter-clockwise"></i> Activité Récente</button>
                                            </div>
                                            <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Options"><i class="ph ph-dots-three"></i></button>
                                        </div>
                                        <div class="ide-panel-content">
                                            <div id="tab-dash-activity" class="sub-pane active flex-col h-full">
                                                <div class="activity-list flex-grow">
                                                    <div class="activity-item">
                                                        <div class="activity-icon bg-blue"><i class="ph ph-file-pdf"></i></div>
                                                        <div class="activity-details">
                                                            <span class="activity-title">Cours_Cardio_P3.pdf</span>
                                                            <span class="activity-time">Il y a 2h • 45 cartes</span>
                                                        </div>
                                                    </div>
                                                    <div class="activity-item">
                                                        <div class="activity-icon bg-green"><i class="ph ph-cards"></i></div>
                                                        <div class="activity-details">
                                                            <span class="activity-title">Médecine/Cardio</span>
                                                            <span class="activity-time">Exporté vers Anki • 3h</span>
                                                        </div>
                                                    </div>
                                                    <div class="activity-item">
                                                        <div class="activity-icon bg-purple"><i class="ph ph-robot"></i></div>
                                                        <div class="activity-details">
                                                            <span class="activity-title">Agent Linter</span>
                                                            <span class="activity-time">Config mise à jour • Hier</span>
                                                        </div>
                                                    </div>
                                                </div>
                                                <button class="btn btn-secondary w-full mt-10 small">Voir tout l'historique</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        """

# Define replacement for other views
edition_start = content.find("<!-- VUE : EDITION / ANALYSE -->")
ab_tests_end = content.find("                    </div>\n                </div>\n            </main>")

other_views_content = """<!-- VUE : EDITION / ANALYSE -->
                        <div class="view" id="view-edition-analyse">
                            <div class="split-view flex-1" style="gap: 12px; height: 100%;">
                                <div class="ide-panel" style="width: 260px;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-ea-explorer"><i class="ph ph-compass"></i> Explorateur</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-ea-explorer" class="sub-pane active flex-col h-full">
                                            <div class="list-area flex-grow mt-10"></div>
                                            <div class="panel-header mt-20"><h3>Filtres (Tags)</h3></div>
                                            <div class="list-area flex-grow mt-10">
                                                <div class="list-item"><i class="ph-fill ph-tag text-yellow mr-5"></i> Tous les tags</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div class="ide-panel flex-1">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-ea-navigator"><i class="ph ph-cards"></i> Cards & Notes Navigator</button>
                                        </div>
                                        <div class="toolbar" style="padding: 0 12px; border-right: 1px solid var(--border-color); margin-right: 8px;">
                                            <button class="btn btn-secondary small"><i class="ph ph-folder-open"></i> Import a deck</button>
                                            <button class="btn btn-primary small ml-5"><i class="ph ph-export"></i> Export to Anki</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-ea-navigator" class="sub-pane active flex-col h-full">
                                            <div class="toolbar border-bottom pb-10">
                                                <span class="muted mr-10">MODE D'AFFICHAGE :</span>
                                                <select class="input-element"><option>Vue : Cartes (Métadonnées)</option></select>
                                                <button class="btn btn-primary ml-auto"><i class="ph ph-plus"></i> Nouvelle Note</button>
                                                <button class="btn btn-secondary ml-10"><i class="ph ph-magic-wand"></i> Modification IA</button>
                                                <button class="btn btn-secondary ml-10"><i class="ph ph-tag"></i> Auto-Tag IA</button>
                                                <button class="btn btn-secondary ml-10"><i class="ph ph-checks"></i> Auditer IA</button>
                                            </div>
                                            <div class="flex-grow center-content flex-col text-muted">
                                                <i class="ph ph-cards mb-10" style="font-size: 40px;"></i>
                                                <h3>Aucune carte à afficher</h3>
                                                <p class="text-center small">Sélectionnez un paquet dans l'explorateur<br>ou créez votre première carte.</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : AI CONSULTANT -->
                        <div class="view" id="view-ai-studio">
                            <div class="split-view flex-1" style="gap: 12px; height: 100%;">
                                <div class="ide-panel flex-1">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-ai-chat"><i class="ph ph-brain"></i> Studio Consultant IA</button>
                                        </div>
                                        <div class="toolbar" style="padding: 0 12px; border-right: 1px solid var(--border-color); margin-right: 8px;">
                                            <select class="input-element"><option>Claude 3.5 Sonnet</option></select>
                                        </div>
                                        <button class="btn-icon small detach-btn" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-ai-chat" class="sub-pane active flex-col h-full">
                                            <div class="chat-history flex-grow center-content flex-col border-bottom pb-15 mb-15">
                                                <i class="ph ph-robot text-muted mb-10" style="font-size: 3rem;"></i>
                                                <h3>Votre Consultant Personnel</h3>
                                                <p class="muted mt-5 text-center">Sélectionnez un document à analyser (@),<br>ou posez directement une question.</p>
                                            </div>
                                            <div class="form-group flex-col mt-auto">
                                                <label class="muted">Contexte : Aucun (L'IA répondra de manière générique)</label>
                                                <div class="relative mt-5">
                                                    <textarea class="textarea-element w-full" rows="4" placeholder="Tapez / pour une commande, ou @ pour charger du contexte (Doc, Paquet)..." style="resize: none;"></textarea>
                                                    <button class="btn btn-primary absolute-bottom-right icon-btn" style="bottom: 15px; right: 15px;"><i class="ph ph-paper-plane-right"></i></button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : LIBRARY -->
                        <div class="view" id="view-library">
                            <div class="split-view flex-1" style="gap: 12px; height: 100%;">
                                <div class="ide-panel" style="width: 220px;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-lib-explorer"><i class="ph ph-folder-open"></i> Explorateur</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-lib-explorer" class="sub-pane active flex-col h-full">
                                            <div class="tabs small mt-10">
                                                <button class="tab active">Docs</button>
                                                <button class="tab">Decks</button>
                                            </div>
                                            <div class="list-area flex-grow mt-10">
                                                <div class="list-item"><i class="ph-fill ph-folder text-blue mr-5"></i> Mes Cours</div>
                                                <div class="list-item"><i class="ph-fill ph-stack text-yellow mr-5"></i> Default Deck</div>
                                            </div>
                                            <div class="toolbar mt-10">
                                                <button class="btn btn-secondary flex-grow"><i class="ph ph-plus"></i></button>
                                                <button class="btn btn-danger icon-btn"><i class="ph ph-trash"></i></button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div class="ide-panel flex-1">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-lib-content"><i class="ph ph-books"></i> Bibliothèque</button>
                                        </div>
                                        <div class="toolbar" style="padding: 0 12px; border-right: 1px solid var(--border-color); margin-right: 8px;">
                                            <button class="btn btn-secondary small"><i class="ph ph-folder-open"></i> Import Deck</button>
                                            <button class="btn btn-secondary small ml-5"><i class="ph ph-globe"></i> Depuis le Web</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content p-0">
                                        <div id="tab-lib-content" class="sub-pane active flex-col h-full p-16" style="padding: 16px;">
                                            <div class="toolbar space-between border-bottom pb-10">
                                                <div class="toolbar-left">
                                                    <select class="input-element"><option>Vue : Cartes (Métadonnées)</option></select>
                                                </div>
                                                <div class="toolbar-right toolbar">
                                                    <button class="btn btn-secondary"><i class="ph ph-plus"></i> Nouvelle Note</button>
                                                </div>
                                            </div>
                                            <div class="table-container flex-grow mt-10">
                                                <table>
                                                    <thead><tr><th>Titre / Front</th><th>Tags</th></tr></thead>
                                                    <tbody><tr><td colspan="2" class="text-center muted p-20">Sélectionnez un dossier ou paquet.</td></tr></tbody>
                                                </table>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div class="ide-panel" style="width: 320px;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-lib-editor"><i class="ph ph-pencil-simple"></i> Éditeur</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-lib-editor" class="sub-pane active flex-col h-full">
                                            <div class="view-scrollable">
                                                <div class="form-group"><label>Tags :</label><input type="text" class="input-element" placeholder="tag1, tag2"></div>
                                                <div class="toolbar wrap gap-5 mt-5 mb-15">
                                                    <button class="btn btn-secondary small flex-grow"><i class="ph ph-magic-wand"></i> Modif IA</button>
                                                    <button class="btn btn-secondary small flex-grow"><i class="ph ph-tag"></i> Auto-Tag</button>
                                                </div>

                                                <div class="toolbar space-between mb-5">
                                                    <h4 style="margin:0;"><i class="ph ph-code"></i> HTML Recto</h4>
                                                </div>
                                                <textarea class="textarea-element w-full code-font" rows="5"></textarea>

                                                <h4 class="mt-15 mb-5" style="margin-top:15px; margin-bottom:5px;"><i class="ph ph-code"></i> HTML Verso</h4>
                                                <textarea class="textarea-element w-full code-font" rows="5"></textarea>
                                            </div>
                                            <div class="toolbar right mt-auto border-top pt-10">
                                                <button class="btn btn-primary"><i class="ph ph-floppy-disk"></i> Sauvegarder</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : CARD MODELS -->
                        <div class="view" id="view-card-models">
                            <div class="split-view flex-1" style="gap: 12px; height: 100%;">
                                <div class="ide-panel" style="width: 250px;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-cm-models"><i class="ph ph-swatches"></i> Modèles</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-cm-models" class="sub-pane active flex-col h-full">
                                            <div class="list-area mt-10 flex-grow">
                                                <div class="list-item active">Texte à trous (Cloze)</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="flex-1 flex-col" style="gap: 12px; overflow: hidden;">
                                    <div class="ide-panel">
                                        <div class="ide-tabs">
                                            <div class="ide-tabs-list">
                                                <button class="ide-tab active" data-target="tab-cm-config"><i class="ph ph-gear"></i> Configuration Globale</button>
                                            </div>
                                            <div class="toolbar" style="padding: 0 12px; border-right: 1px solid var(--border-color); margin-right: 8px;">
                                                <button class="btn btn-secondary small"><i class="ph ph-plus"></i> Nouveau Modèle</button>
                                                <button class="btn btn-secondary small ml-5"><i class="ph ph-arrows-clockwise"></i> Rafraîchir</button>
                                            </div>
                                            <button class="btn-icon small detach-btn" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                        </div>
                                        <div class="ide-panel-content">
                                            <div id="tab-cm-config" class="sub-pane active flex-col">
                                                <div class="form-group">
                                                    <label class="muted uppercase small">Champs de données (séparés par des virgules) :</label>
                                                    <input type="text" class="input-element w-full mt-5">
                                                </div>
                                                <div class="form-group mt-15">
                                                    <label class="muted uppercase small">Style Global (CSS) :</label>
                                                    <textarea class="textarea-element w-full mt-5 code-font" rows="4"></textarea>
                                                </div>
                                                <div class="toolbar right mt-15">
                                                    <button class="btn btn-danger mr-10"><i class="ph ph-trash"></i> Supprimer</button>
                                                    <button class="btn btn-primary"><i class="ph ph-floppy-disk"></i> Sauvegarder</button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div class="ide-panel flex-1">
                                        <div class="ide-tabs">
                                            <div class="ide-tabs-list">
                                                <button class="ide-tab active" data-target="tab-cm-editor"><i class="ph ph-pencil-simple"></i> Éditeur de Cartes</button>
                                            </div>
                                            <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                        </div>
                                        <div class="ide-panel-content">
                                            <div id="tab-cm-editor" class="sub-pane active flex-col h-full">
                                                <div class="toolbar border-bottom pb-10">
                                                    <span class="muted uppercase small mr-10">Sélection de la carte :</span>
                                                    <input type="text" class="input-element" style="width: 150px;">
                                                    <button class="btn btn-secondary icon-btn ml-5"><i class="ph ph-plus"></i></button>
                                                    <button class="btn btn-secondary icon-btn ml-5"><i class="ph ph-pencil-simple"></i></button>
                                                    <button class="btn btn-secondary icon-btn ml-5"><i class="ph ph-trash"></i></button>

                                                    <button class="btn btn-secondary ml-auto"><i class="ph ph-corners-out"></i> Mode Focus</button>
                                                    <span class="muted uppercase small ml-15 mr-10">Prévisualisation :</span>
                                                    <select class="input-element"><option>Voir Recto</option></select>
                                                </div>
                                                <div class="view-scrollable pr-10 mt-10">
                                                    <div class="toolbar gap-5">
                                                        <button class="tag-btn">{{Champ}}</button>
                                                        <button class="tag-btn">{{FrontSide}}</button>
                                                        <button class="tag-btn">{{cloze:Champ}}</button>
                                                    </div>
                                                    <div class="form-group mt-15">
                                                        <label class="muted uppercase small">HTML du Recto :</label>
                                                        <textarea class="textarea-element w-full mt-5 code-font" rows="5"></textarea>
                                                    </div>
                                                    <div class="form-group mt-15">
                                                        <label class="muted uppercase small">HTML du Verso :</label>
                                                        <textarea class="textarea-element w-full mt-5 code-font" rows="5"></textarea>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : BATCH FACTORY -->
                        <div class="view" id="view-batch-factory">
                            <div class="split-view flex-1" style="justify-content: center; padding: 20px; height: 100%;">
                                <div class="ide-panel flex-col w-full" style="max-width: 800px; height: fit-content;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-batch"><i class="ph ph-factory"></i> Batch Factory</button>
                                        </div>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-batch" class="sub-pane active flex-col h-full">
                                            <p class="muted mb-20">Lancez la génération de cartes en arrière-plan sur une file d'attente de documents.</p>
                                            <div class="form-group"><label>Découpage Sémantique :</label><select class="input-element"><option>Automatique par chapitres</option></select></div>
                                            <div class="table-container mt-10" style="height: 250px;">
                                                <table>
                                                    <thead><tr><th>Document</th><th>Progression</th><th>Statut</th></tr></thead>
                                                    <tbody><tr><td colspan="3" class="text-center muted p-20">Déposez des documents ici pour les ajouter à la file.</td></tr></tbody>
                                                </table>
                                            </div>
                                            <div class="toolbar mt-20 center-content">
                                                <button class="btn btn-primary" style="font-size: 16px; padding: 12px 24px;"><i class="ph ph-rocket-launch"></i> Démarrer l'Usine</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : AGENTS -->
                        <div class="view" id="view-agents">
                            <div class="split-view flex-1" style="gap: 12px; height: 100%;">
                                <div class="ide-panel" style="width: 250px;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-agents-list"><i class="ph ph-users"></i> Agents IA</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-agents-list" class="sub-pane active flex-col h-full">
                                            <div class="list-area flex-grow mt-10">
                                                <div class="list-item active">Linter & Qualité</div>
                                                <div class="list-item">Archiviste</div>
                                                <div class="list-item">Générateur QA</div>
                                            </div>
                                            <button class="btn btn-secondary w-full mt-10"><i class="ph ph-plus"></i> Nouvel Agent</button>
                                        </div>
                                    </div>
                                </div>
                                <div class="ide-panel flex-1">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-agents-editor"><i class="ph ph-robot"></i> Éditeur d'Agents IA</button>
                                        </div>
                                        <button class="btn-icon small detach-btn" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-agents-editor" class="sub-pane active flex-col h-full">
                                            <div class="form-group"><label>Nom de l'Agent :</label><input type="text" class="input-element" value="Linter Qualité"></div>
                                            <div class="form-group mt-10 flex-grow flex-col">
                                                <label>Prompt Jinja2 :</label>
                                                <textarea class="textarea-element w-full code-font flex-grow" style="resize: none;">Tu es un expert...</textarea>
                                            </div>
                                            <div class="form-group mt-10"><label>Format de sortie :</label><select class="input-element"><option>JSON Strict</option></select></div>
                                            <div class="toolbar right mt-20">
                                                <button class="btn btn-danger mr-auto"><i class="ph ph-trash"></i> Supprimer</button>
                                                <button class="btn btn-primary"><i class="ph ph-floppy-disk"></i> Sauvegarder</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : PIPELINES -->
                        <div class="view" id="view-pipelines">
                            <div class="split-view flex-1" style="justify-content: center; padding: 20px; height: 100%;">
                                <div class="ide-panel flex-col w-full" style="max-width: 800px; height: fit-content;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-pipelines"><i class="ph ph-git-merge"></i> Pipelines de Génération</button>
                                        </div>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-pipelines" class="sub-pane active flex-col h-full">
                                            <div class="form-group"><label>Pipeline Actif :</label><select class="input-element"><option>Excellence (Standard)</option></select></div>
                                            <div class="list-area mt-20 p-10" style="border-radius: var(--radius-sm); min-height: 200px; border: 1px solid var(--border-color); background: var(--bg-secondary);">
                                                <div class="list-item" style="background: var(--bg-primary); border: 1px solid var(--border-color); margin-bottom: 8px; border-radius: var(--radius-sm); padding: 12px;"><i class="ph ph-dots-six-vertical text-muted mr-10"></i> 1. Archiviste (Extraction)</div>
                                                <div class="list-item" style="background: var(--bg-primary); border: 1px solid var(--border-color); margin-bottom: 8px; border-radius: var(--radius-sm); padding: 12px;"><i class="ph ph-dots-six-vertical text-muted mr-10"></i> 2. Générateur QA</div>
                                                <div class="list-item" style="background: var(--bg-primary); border: 1px solid var(--border-color); margin-bottom: 8px; border-radius: var(--radius-sm); padding: 12px;"><i class="ph ph-dots-six-vertical text-muted mr-10"></i> 3. Linter (Validation)</div>
                                            </div>
                                            <div class="toolbar mt-20 space-between">
                                                <select class="input-element flex-grow"><option>Ajouter un Agent à la chaîne...</option></select>
                                                <button class="btn btn-secondary ml-10"><i class="ph ph-plus"></i> Ajouter</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- VUE : AB TESTS -->
                        <div class="view" id="view-ab-tests">
                            <div class="split-view flex-1" style="justify-content: center; padding: 20px; height: 100%;">
                                <div class="ide-panel flex-col w-full" style="max-width: 800px; height: fit-content;">
                                    <div class="ide-tabs">
                                        <div class="ide-tabs-list">
                                            <button class="ide-tab active" data-target="tab-ab-tests"><i class="ph ph-scales"></i> Tests A/B</button>
                                        </div>
                                    </div>
                                    <div class="ide-panel-content">
                                        <div id="tab-ab-tests" class="sub-pane active flex-col h-full">
                                            <p class="muted mb-20">Configurez une comparaison entre deux moteurs IA ou deux pipelines pour évaluer la qualité des cartes générées sur un même texte source.</p>
                                            <div class="form-group"><label>Sujet de test (Document) :</label><select class="input-element"><option>Extrait Cardio P3</option></select></div>
                                            <div class="grid-3 mt-20 gap-20">
                                                <div class="form-group" style="grid-column: span 1;"><label>Moteur A :</label><select class="input-element"><option>Claude 3.5 Sonnet</option></select></div>
                                                <div class="center-content text-muted" style="font-size: 24px; font-weight: bold;">VS</div>
                                                <div class="form-group" style="grid-column: span 1;"><label>Moteur B :</label><select class="input-element"><option>GPT-4o</option></select></div>
                                            </div>
                                            <div class="toolbar center-content mt-30">
                                                <button class="btn btn-primary" style="font-size: 16px; padding: 12px 24px;"><i class="ph ph-play"></i> Lancer la Confrontation</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
"""

new_content = content[:dashboard_start] + dashboard_content + content[forge_start:edition_start] + other_views_content + content[ab_tests_end:]

with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/maquette/concept_ide/index.html", "w") as f:
    f.write(new_content)

print("Replacement done!")
