import json
from dataclasses import dataclass
from typing import Any


def is_instance_valid(message: str, instance_type: dataclass) -> (bool, str):
    # Проверяем полученную строку на валидность преобразования в json и на то, что полученный json
    # имеет требуемую структуру
    try:
        instance_type(**json.loads(message))
    except json.JSONDecodeError:
        return (
            False,
            '{"errors": ["Requires valid JSON"], "msgType": "Errors"}',
        )
    except TypeError:
        return (
            False,
            '{"errors": ["Requires msgType specified"], "msgType": "Errors"}',
        )
    except ValueError as e:
        return False, '{"errors": ["%s"], "msgType": "Errors"}' % (str(e),)

    return True, message
