import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    errors: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 5,
      maxVUs: 20,
    },
  },
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/fail`, {
    timeout: '5s',
  });
  check(response, {
    'intentional HTTP 500': (r) => r.status === 500,
  });
}
