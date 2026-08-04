from ankiforge.database.models import db, PipelineModel, PipelineStepModel

db.connect()
pipelines = list(PipelineModel.select())
for p in pipelines:
    print(f"Pipeline: {p.name}")
    for s in p.steps:
        print(f"  Step: {s.step_type} - {s.persona.name if s.persona else 'None'}")
