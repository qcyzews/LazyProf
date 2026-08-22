# /backend/tests/services/test_arxiv_service.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.arxiv_service import ArxivService

# Przykładowy XML z API arXiv
MOCK_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...</summary>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>
"""

@pytest.mark.asyncio
async def test_fetch_paper_metadata_success():
    """Testuje poprawne parsowanie odpowiedzi XML z API arXiv."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = MOCK_ARXIV_XML
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        metadata = await ArxivService.fetch_paper_metadata("1706.03762")

    assert metadata["arxiv_id"] == "1706.03762"
    assert metadata["title"] == "Attention Is All You Need"
    assert metadata["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert metadata["published"] == "2017-06-12"
    assert metadata["pdf_url"] == "https://arxiv.org/pdf/1706.03762.pdf"

@pytest.mark.asyncio
async def test_fetch_paper_metadata_fallback_on_error():
    """Testuje przejście w tryb fallback przy błędzie HTTP."""
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection Error")):
        metadata = await ArxivService.fetch_paper_metadata("1706.03762")

    assert metadata["arxiv_id"] == "1706.03762"
    assert metadata["title"] == "Paper arXiv:1706.03762"
    assert metadata["authors"] == ["Unknown Authors"]
    assert metadata["published"] == "N/A"

@pytest.mark.asyncio
@patch("app.services.arxiv_service.httpx.AsyncClient.get")
async def test_arxiv_service_fetch_metadata(mock_httpx_get):
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Test Title</title>
        <summary>Summary</summary>
        <author><name>Author</name></author>
        <published>2021-01-01T00:00:00Z</published>
        <id>http://arxiv.org/abs/2106.09685v1</id>
        <link title="pdf" href="http://arxiv.org/pdf/2106.09685v1" rel="related" type="application/pdf"/>
      </entry>
    </feed>"""

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = xml_content.encode("utf-8")
    mock_response.text = xml_content
    mock_response.raise_for_status = MagicMock()

    mock_httpx_get.return_value = mock_response

    meta = await ArxivService.fetch_paper_metadata("2106.09685")
    assert meta["title"] == "Test Title" 