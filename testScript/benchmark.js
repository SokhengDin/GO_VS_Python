import http from 'k6/http';
import { check, sleep } from 'k6';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';
import { SharedArray } from 'k6/data';

// Read URL from environment variable
const apiUrl = __ENV.API_URL;
const FLOOD_MODE = __ENV.FLOOD_MODE || 'false';

// Pregenerate user and pet data to reduce CPU overhead during tests
const users = new SharedArray('users', function() {
  const data = [];
  for (let i = 0; i < 1000; i++) {
    const firstName = randomString(8);
    const lastName = randomString(8);
    data.push({
      name: `${firstName} ${lastName}`,
      first_name: firstName,
      last_name: lastName,
      is_active: true
    });
  }
  return data;
});

const pets = new SharedArray('pets', function() {
  const petTypes = ['dog', 'cat', 'bird', 'hamster', 'rabbit', 'fish'];
  const data = [];
  for (let i = 0; i < 1000; i++) {
    data.push({
      name: randomString(8),
      type: petTypes[Math.floor(Math.random() * petTypes.length)],
      is_active: true
    });
  }
  return data;
});

// Extreme load test configuration
export const options = {
  scenarios: {
    // Sustained extreme load
    extreme_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 500 },    // Fast ramp-up to 500 users
        { duration: '1m', target: 1000 },    // Ramp to 1000 users
        { duration: '2m', target: 1000 },    // Sustain 1000 users
        { duration: '1m', target: 1500 },    // Increase to 1500 users
        { duration: '1m', target: 1500 },    // Sustain 1500 users
        { duration: '30s', target: 0 },      // Ramp-down
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1000'],       // 95% of requests should be below 1000ms
    http_req_failed: ['rate<0.15'],          // Less than 15% of requests should fail
  },
  discardResponseBodies: true,               // Discard response bodies to reduce memory usage
};

// Add flood scenario only if FLOOD_MODE is true
if (FLOOD_MODE === 'true') {
  options.scenarios.flood = {
    executor: 'constant-arrival-rate',
    rate: 1000,                            // 1000 iterations per second
    timeUnit: '1s',                        // 1 second
    duration: '20s',                       // Run for 20 seconds
    preAllocatedVUs: 2000,                 // Preallocate 2000 VUs
    maxVUs: 3000,                          // Maximum 3000 VUs
    startTime: '3m',                       // Start after 3 minutes into the test
    exec: 'floodRequest',                  // Use the floodRequest function
  };
}

function getRandomUser() {
  return users[Math.floor(Math.random() * users.length)];
}

function getRandomPet() {
  return pets[Math.floor(Math.random() * pets.length)];
}

// Default function for the main load test
export default function() {
  const headers = { 'Content-Type': 'application/json' };
  
  // Create User
  const userData = getRandomUser();
  const response = http.post(`${apiUrl}/api/v1/users`, JSON.stringify(userData), { headers });
  
  if (check(response, { 'status is 201': (r) => r.status === 201 })) {
    try {
      const userId = response.json().id;
      
      // Add 1-3 Pets to User (depending on system capacity)
      const petCount = Math.floor(Math.random() * 3) + 1;
      for (let i = 0; i < petCount; i++) {
        const petData = getRandomPet();
        http.post(`${apiUrl}/api/v1/users/${userId}/pets`, JSON.stringify(petData), { headers });
      }
      
      // Get User with Pets
      http.get(`${apiUrl}/api/v1/users/${userId}`);
    } catch (e) {
      // Silently continue on errors to maintain load
    }
  }
  
  // Almost no sleep to maximize throughput
  sleep(Math.random() * 0.2);  // Sleep for 0-200ms
}

// Function specifically for the flood scenario - simpler and faster
export function floodRequest() {
  const headers = { 'Content-Type': 'application/json' };
  
  // Just create users at maximum rate
  const userData = getRandomUser();
  http.post(`${apiUrl}/api/v1/users`, JSON.stringify(userData), { 
    headers,
    timeout: '500ms' // Short timeout for flood test
  });
  
  // No sleep in flood mode to maximize request rate
}

