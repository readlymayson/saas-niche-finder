from app.services.natasha_entities import NatashaEntityService


def test_natasha_service_smoke_empty_text() -> None:
    service = NatashaEntityService()
    entities = service.extract("")
    assert entities.organizations == []
    assert entities.persons == []
    assert entities.locations == []


def test_natasha_service_fallback_org_pattern() -> None:
    service = NatashaEntityService()
    entities = service.extract("Клиент: ООО Ромашка внедряет новый сервис.")
    assert isinstance(entities.organizations, list)
