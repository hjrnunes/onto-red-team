from refiner.models import KnowledgeBaseRef, RiskDetail

print('KnowledgeBaseRef fields:')
for name, field in KnowledgeBaseRef.model_fields.items():
    print(f'  {name}: {field.annotation} (default={field.default})')

print('\nRiskDetail fields:')
for name, field in RiskDetail.model_fields.items():
    print(f'  {name}: {field.annotation} (default={field.default})')
