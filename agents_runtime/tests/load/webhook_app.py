from unittest.mock import MagicMock

import core.pubsub_publisher


publisher = MagicMock()
publisher.publish.side_effect = lambda payload, **kwargs: f"load-{payload['request_id']}"
core.pubsub_publisher.get_publisher = lambda: publisher

