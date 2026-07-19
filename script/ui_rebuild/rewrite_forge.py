html_file = "/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/maquette/concept_ide/index.html"

with open(html_file, "r") as f:
    content = f.read()

# We need to replace everything from "<!-- COL 2 : Source & Résultats" down to the end of view-forge.
start_marker = "<!-- COL 2 : Source & Résultats"
end_marker = "<!-- VUE : EDITION / ANALYSE -->"

if start_marker in content and end_marker in content:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    new_html = """<!-- COL 2 : Source (Top) & Cartes Générées (Bottom) -->
                                <div class="flex-col flex-1" style="gap: 12px; min-width: 0;">
                                    <!-- Source Panel -->
                                    <div class="ide-panel" style="flex: 0 0 35%;">
                                        <div class="ide-tabs" style="align-items: center;">
                                            <div class="ide-tabs-list" style="display: flex; flex: 1; overflow-x: auto;">
                                                <button class="ide-tab active" draggable="true" data-target="tab-source"><i class="ph ph-text-align-left"></i> Document Source</button>
                                            </div>
                                            <button class="btn-icon small detach-btn" style="margin-left: auto; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                        </div>
                                        <div class="ide-panel-content">
                                            <div id="tab-source" class="sub-pane active h-full flex-col">
                                                <div class="toolbar">
                                                    <select class="input-element flex-grow"><option>-- Sélectionner un document --</option></select>
                                                    <button class="btn btn-secondary icon-btn"><i class="ph ph-arrows-clockwise"></i></button>
                                                </div>
                                                <textarea class="textarea-element w-full mt-10 flex-grow" style="resize: none;" placeholder="Collez votre texte source ici ou sélectionnez un document..."></textarea>
                                                <div class="toolbar space-between mt-10">
                                                    <span class="muted small">Tokens estimés : 0</span>
                                                    <button class="btn btn-primary"><i class="ph ph-magic-wand"></i> Générer les Cartes</button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- Unified Résultats & Preview Panel -->
                                    <div class="ide-panel flex-1">
                                        <div class="ide-tabs" style="align-items: center;">
                                            <div class="ide-tabs-list" style="display: flex; flex: 1; overflow-x: auto;">
                                                <button class="ide-tab active" draggable="true" data-target="tab-resultats"><i class="ph ph-list-numbers"></i> Cartes Générées (2)</button>
                                                <button class="ide-tab" draggable="true" data-target="tab-erreurs"><i class="ph ph-warning-circle"></i> Erreurs</button>
                                            </div>
                                            
                                            <!-- IDEA-like Preview Toggles -->
                                            <div class="view-toggles" style="display: flex; gap: 4px; padding: 0 12px; border-right: 1px solid var(--border-color); margin-right: 8px;">
                                                <button class="btn-icon small" title="Liste uniquement (Editor Only)"><i class="ph ph-list-dashes"></i></button>
                                                <button class="btn-icon small active" title="Split View (Editor and Preview)" style="background: var(--bg-hover); color: var(--text-primary);"><i class="ph ph-columns"></i></button>
                                                <button class="btn-icon small" title="Preview uniquement"><i class="ph ph-monitor"></i></button>
                                            </div>

                                            <button class="btn-icon small detach-btn" style="margin-left: 0; margin-right: 4px;" title="Détacher"><i class="ph ph-arrow-up-right"></i></button>
                                        </div>
                                        
                                        <div class="ide-panel-content p-0" style="padding: 0;">
                                            <div id="tab-resultats" class="sub-pane active h-full flex-row w-full">
                                                <!-- LEFT SIDE : Table -->
                                                <div class="flex-1 flex-col" style="padding: 16px; border-right: 1px solid var(--border-color);">
                                                    <div class="table-container flex-grow">
                                                        <table>
                                                            <thead><tr><th>Recto</th><th>Verso</th><th>Statut</th></tr></thead>
                                                            <tbody>
                                                                <tr style="cursor: pointer;" class="active-row"><td>La capitale de la France ?</td><td>Paris</td><td><span class="badge text-green">Prêt</span></td></tr>
                                                                <tr style="cursor: pointer;"><td>Symbole chimique de l'eau ?</td><td>H2O</td><td><span class="badge text-green">Prêt</span></td></tr>
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                    <div class="toolbar right mt-10">
                                                        <button class="btn btn-primary"><i class="ph ph-floppy-disk"></i> Sauvegarder dans Anki</button>
                                                    </div>
                                                </div>
                                                
                                                <!-- RIGHT SIDE : Preview -->
                                                <div class="flex-1 flex-col" style="padding: 16px; background-color: rgba(0,0,0,0.1);">
                                                    <div class="preview-card-container flex-grow">
                                                        <div class="flashcard-wrapper">
                                                            <div class="preview-side">La capitale de la France ?</div>
                                                            <div class="preview-divider">Verso</div>
                                                            <div class="preview-side" style="color: var(--accent-primary); font-weight: 500;">Paris</div>
                                                        </div>
                                                    </div>
                                                    <div class="toolbar space-between mt-16" style="gap: 12px;">
                                                        <button class="btn btn-secondary flex-1" style="justify-content: center;"><i class="ph ph-pencil-simple"></i> Éditer</button>
                                                        <button class="btn btn-secondary text-red flex-1" style="justify-content: center;"><i class="ph ph-trash"></i> Rejeter</button>
                                                    </div>
                                                </div>
                                            </div>
                                            <div id="tab-erreurs" class="sub-pane hidden h-full flex-col" style="padding: 16px;">
                                                <p class="muted">Aucune erreur lors de la génération.</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        """

    # We also need to remove the closing tags properly
    # The end_marker is <!-- VUE : EDITION / ANALYSE -->

    new_content = content[:start_idx] + new_html + content[end_idx:]
    with open(html_file, "w") as f:
        f.write(new_content)
    print("REPLACED")
else:
    print("MARKER NOT FOUND")
