import http from 'k6/http';
import { check, sleep } from 'k6';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Read URL from environment variable
const apiUrl = __ENV.API_URL;

export const options = {
  stages: [
    { duration: '20s', target: 100 },    // Ramp up to 100 users in 20 seconds
    { duration: '30s', target: 300 },    // Ramp up to 300 users in 30 seconds
    { duration: '1m', target: 500 },     // Ramp up to 500 users over 1 minute
    { duration: '2m', target: 500 },     // Stay at 500 users for 2 minutes
    { duration: '30s', target: 0 },      // Ramp down to 0 users
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],    // Less than 5% of requests should fail
    http_req_duration: ['p(95)<500'],  // 95% of requests should be below 500ms
  },
};

function generateUser() {
  const firstName = randomString(8);
  const lastName = randomString(8);
  
  return {
    name: `${firstName} ${lastName}`,
    first_name: firstName,
    last_name: lastName,
    is_active: true
  };
}

function generatePet() {
  const petTypes = ['dog', 'cat', 'bird'];
  return {
    name: randomString(8),
    type: petTypes[Math.floor(Math.random() * petTypes.length)],
    is_active: true
  };
}

export default function() {
  const headers = { 'Content-Type': 'application/json' };
  
  // Create User
  const userData = generateUser();
  const response = http.post(`${apiUrl}/api/v1/users`, JSON.stringify(userData), { headers });
  
  if (check(response, { 'status is 201': (r) => r.status === 201 })) {
    const userId = response.json().id;
    
    // Add Pet to User
    const petData = generatePet();
    http.post(`${apiUrl}/api/v1/users/${userId}/pets`, JSON.stringify(petData), { headers });
    
    // Get User with Pets
    http.get(`${apiUrl}/api/v1/users/${userId}`);
  }
  
  // Reduced sleep time to 0.1 seconds instead of 1 second
  sleep(0.1);
}
