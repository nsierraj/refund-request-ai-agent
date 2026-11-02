"""Step 9: send traces to Phoenix, a tracing dashboard running on your Mac.

    docker run -d --name phoenix -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:14.9.1
    open http://localhost:6006

How it fits together, using OpenTelemetry (OTel), the standard most
tracing tools speak:

  Strands  --spans-->  OpenInference processor  --OTLP over HTTP-->  Phoenix
  (already emits       (relabels them so Phoenix        (stores and shows
   a span per agent     knows which spans are LLM        them at :6006)
   turn, model call     calls, tools, agents)
   and tool call)

A span is one timed step with a name, a start, an end, attributes
(model, tokens, tool input and output...) and a parent. A trace is the
tree of spans for one request.
"""

import os
import urllib.request

from openinference.instrumentation.strands_agents import StrandsAgentsToOpenInferenceProcessor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

PHOENIX_URL = os.environ.get("PHOENIX_URL", "http://localhost:6006")
PROJECT = "refund-agent"


def _phoenix_is_up() -> bool:
    try:
        urllib.request.urlopen(PHOENIX_URL, timeout=1)
        return True
    except Exception:
        return False


def setup_tracing() -> bool:
    """Call once, before building the agent. Returns False if Phoenix isn't running."""
    if not _phoenix_is_up():
        print(f"  (Phoenix isn't answering at {PHOENIX_URL}, so no traces this run. "
              "Start it with the docker command in tracing.py.)\n")
        return False

    provider = TracerProvider(resource=Resource.create({
        "service.name": PROJECT,
        "openinference.project.name": PROJECT,  # the project Phoenix files these traces under
    }))
    # Order matters: relabel each span first, then export it.
    provider.add_span_processor(StrandsAgentsToOpenInferenceProcessor())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{PHOENIX_URL}/v1/traces")))
    trace.set_tracer_provider(provider)  # Strands picks up whatever provider is set globally
    print(f"  Tracing on. Open {PHOENIX_URL} and pick the '{PROJECT}' project.\n")
    return True


tracer = trace.get_tracer(PROJECT)  # for spans we add ourselves
