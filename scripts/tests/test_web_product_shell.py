"""A shared SPA entry must use its installed product's logo and identity."""
import json
import re

import pytest
from lib import product_identity


@pytest.mark.parametrize('existing', ['',
    '<script type="application/json" id="cx-product-identity">{"brand_key":"chuanxu"}</script>'])
@pytest.mark.parametrize('brand', ['agentx', 'chuanxu'])
def test_shared_or_stale_shell_uses_exact_installed_product(monkeypatch, existing, brand):
    product = {'brand_key': brand, 'logo': '/static/brand/' + brand + '.png',
               'brand_zh': 'Label </script><script>unsafe</script>'}
    monkeypatch.setattr(product_identity, 'identity', lambda root=None: product)
    document = '<html><head>' + existing + '<script src="/static/assets/app.js"></script></head><body></body></html>'
    result = product_identity.web_shell(document)
    assert result.count('id="cx-product-identity"') == 1
    payload = re.search(r'id="cx-product-identity">(.*?)</script>', result)[1]
    assert json.loads(payload) == product and '<' not in payload
    assert '<script src="/static/assets/app.js"></script>' in result
    assert result.index('id="cx-product-identity"') < result.index('</head>')
    assert product_identity.web_shell(result) == result


def test_malformed_shell_fails_before_serving_an_unbound_page():
    with pytest.raises(ValueError, match='head boundary'):
        product_identity.web_shell('<html><body></body></html>')
