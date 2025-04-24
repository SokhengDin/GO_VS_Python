import http from 'k6/http';
import { check, sleep } from 'k6';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Read URL from environment variable
const apiUrl = __ENV.API_URL;

export const options = {
  stages: [
    { duration: '30s', target: 50 },
    { duration: '1m', target: 100 },
    { duration: '30s', target: 0 },
  ],
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
  
  sleep(1);
}
