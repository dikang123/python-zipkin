
import requests.sessions

from zipkin import local
from zipkin.models import Annotation
from zipkin.util import hex_str


def pre_request(request):
    parent_trace = local().current
    request.trace = parent_trace.child("requests:%s %s" % (request.method, request.url))
    forwarded_trace = request.trace.child_noref("subservice")

    request.headers['X-B3-TraceId'] = hex_str(forwarded_trace.trace_id)
    request.headers['X-B3-SpanId'] = hex_str(forwarded_trace.span_id)
    if forwarded_trace.parent_span_id is not None:
        request.headers['X-B3-ParentSpanId'] = hex_str(forwarded_trace.parent_span_id)

    request.trace.record(Annotation.string('http.uri', request.url))
    request.trace.record(Annotation.server_recv())

    return request


def pre_response(resp, req=None):
    if not req:
        req = resp.request

    req.trace.record(Annotation.string('http.responsecode', '{0}'.format(getattr(resp, 'status', None))))
    req.trace.record(Annotation.server_send())

    return resp


try:
    from requests.adapters import HTTPAdapter

    class ZipkinHTTPAdapter(HTTPAdapter):
        def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
            pre_request(request)
            return super(ZipkinHTTPAdapter, self).send(request, stream, timeout, verify, cert, proxies)

        def build_response(self, req, resp):
            pre_response(resp, req)

            return super(ZipkinHTTPAdapter, self).build_response(req, resp)

except ImportError:
    # requests < 1.0.0
    pass


def _func(init):
    def func(self, *args, **kwargs):
        init(self, *args, **kwargs)
        if hasattr(self, 'mount'):
            self.mount('http://', ZipkinHTTPAdapter())
            self.mount('https://', ZipkinHTTPAdapter())
        else:
            self.hooks['pre_request'] = pre_request
            self.hooks['response'] = pre_response
    return func


def bind():
    old_init = requests.sessions.Session.__init__
    requests.sessions.Session.__init__ = _func(old_init)
