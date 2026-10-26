import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orders: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 5),
      timeUnit: '1s',
      duration: __ENV.DURATION || '10m',
      preAllocatedVUs: 5,
      maxVUs: 20,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const response = http.post(
    `${__ENV.BASE_URL}/order`,
    JSON.stringify({ item: 'lab4-load', quantity: 1 }),
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '5s',
    },
  );

  check(response, {
    'order created: HTTP 201': (r) => r.status === 201,
  });
}
