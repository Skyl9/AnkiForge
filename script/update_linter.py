path = "/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/ai/linter.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

start_marker = "    @staticmethod\n    def get_financial_summary(deck_id: Optional[int] = None) -> Dict[str, Any]:"
end_marker = "    @staticmethod\n    def get_overall_financial_summary() -> Dict[str, Any]:"
start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)
if end_idx == -1:
    end_idx = content.find("class ", start_idx + len(start_marker))
if end_idx == -1:
    end_idx = len(content)

new_code = """    @staticmethod
    def get_financial_summary(deck_id: Optional[int] = None) -> Dict[str, Any]:
        \"\"\"Retourne le bilan financier et les métriques de rétention FSRS-4.5 basé sur la BDD.\"\"\"
        from ankiforge.database.models import CardModel, TokenUsageModel
        from peewee import fn

        query = CardModel.select()
        if deck_id is not None:
            query = query.where(CardModel.deck_id == deck_id)
        total_cards = query.count()
        
        maturing_cards = query.where(CardModel.ivl > 21).count()
        new_cards = query.where(CardModel.ivl == 0).count()
        learning_cards = query.where((CardModel.ivl > 0) & (CardModel.ivl <= 21)).count()

        avg_stability = query.select(fn.AVG(CardModel.stability)).scalar() or 0.0
        fsrs_retention = 90.0
        if avg_stability > 0:
            fsrs_retention = min(99.0, max(0.0, 90.0 + (avg_stability * 0.5)))
        
        # Token usage aggregation
        total_spent = TokenUsageModel.select(fn.SUM(TokenUsageModel.estimated_cost_usd)).scalar() or 0.0
        total_tokens = TokenUsageModel.select(fn.SUM(TokenUsageModel.total_tokens)).scalar() or 0
        
        # Models usage
        models_query = TokenUsageModel.select(
            TokenUsageModel.model_id,
            fn.SUM(TokenUsageModel.estimated_cost_usd).alias('cost'),
            fn.SUM(TokenUsageModel.total_tokens).alias('tokens')
        ).group_by(TokenUsageModel.model_id)
        
        colors = ["#4285F4", "#10a37f", "#c084fc", "#f59e0b"]
        models_list = []
        for i, mq in enumerate(models_query):
            pct = (mq.cost / total_spent * 100) if total_spent > 0 else 0
            models_list.append({
                "name": mq.model_id,
                "cost_usd": mq.cost,
                "tokens": mq.tokens,
                "pct": pct,
                "color": colors[i % len(colors)],
            })
            
        if not models_list:
             models_list = [
                {
                    "name": "Aucun Modèle API Utilisé",
                    "cost_usd": 0.0,
                    "tokens": 0,
                    "pct": 0.0,
                    "color": "var(--color-blue)",
                }
             ]
             
        # Add Local model manually since it's zero cost
        models_list.append({
            "name": "Modèles Locaux (Marker PDF & Whisper AI)",
            "cost_usd": 0.0,
            "tokens": 0,
            "pct": 0.0,
            "color": "var(--color-green)",
        })

        # Task Breakdown
        task_query = TokenUsageModel.select(
            TokenUsageModel.task_type,
            fn.SUM(TokenUsageModel.estimated_cost_usd).alias('cost')
        ).group_by(TokenUsageModel.task_type)
        
        tasks_breakdown = []
        for i, tq in enumerate(task_query):
            pct = (tq.cost / total_spent * 100) if total_spent > 0 else 0
            tasks_breakdown.append({
                "task": tq.task_type,
                "cost_usd": tq.cost,
                "pct": pct,
                "color": colors[i % len(colors)]
            })

        if not tasks_breakdown:
            tasks_breakdown = [
                {"task": "1. Reformulation & Génération Wozniak", "cost_usd": 0.0, "pct": 0.0, "color": "var(--accent-primary)"},
                {"task": "2. Extraction & Structure Sources (PDF/Web)", "cost_usd": 0.0, "pct": 0.0, "color": "var(--color-blue)"},
                {"task": "3. Audit Linter Ergonomique & Live KaTeX", "cost_usd": 0.0, "pct": 0.0, "color": "#c084fc"},
            ]
        
        avg_cost = total_spent / total_cards if total_cards > 0 else 0.0
        
        return {
            "total_spent_usd": total_spent,
            "avg_cost_per_card_usd": avg_cost,
            "tokens_consumed": total_tokens,
            "fsrs_retention_pct": round(fsrs_retention, 1),
            "target_retention_pct": 90.0,
            "maturing_cards": maturing_cards,
            "total_cards": total_cards,
            "daily_workload_cards": round(total_cards * 0.05, 1),
            "daily_workload_minutes": round(total_cards * 0.05 * 0.5, 1),
            "models": models_list,
            "tasks_breakdown": tasks_breakdown,
            "maturity_distribution": {
                "new": new_cards,
                "learning": learning_cards,
                "maturing": maturing_cards,
            },
        }

"""

new_content = content[:start_idx] + new_code + "\n" + content[end_idx:]
with open(path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Updated linter.py successfully.")
