export const FIXTURE_DATE = "2026-06-16";
export const ALTERNATE_FIXTURE_DATE = "2026-06-18";

export const BOOKING_PROVIDER = Object.freeze({
  name: "Harbor Point Clinic",
  address: "24 Cedar Lane, Northbridge",
  email: "appointments@harborpoint.example",
  phone: "555-0168",
  arrivalNote:
    "Use the Cedar Lane entrance and check in at reception on the ground floor.",
});

export const SERVICES = [
  {
    id: "svc-consultation",
    name: "Consultation",
    duration: "30 minutes",
    description: "Initial planning appointment for the benchmark fixture.",
  },
  {
    id: "svc-repair-assessment",
    name: "Repair assessment",
    duration: "45 minutes",
    description: "Assessment appointment with a longer fixed duration.",
  },
  {
    id: "svc-follow-up-call",
    name: "Follow-up call",
    duration: "15 minutes",
    description: "Short follow-up appointment for contrast in the service list.",
  },
];

export const AVAILABILITY = {
  [FIXTURE_DATE]: [
    {
      time: "09:00",
      available: true,
    },
    {
      time: "10:30",
      available: false,
    },
    {
      time: "13:00",
      available: true,
    },
    {
      time: "15:30",
      available: true,
    },
  ],
  [ALTERNATE_FIXTURE_DATE]: [
    {
      time: "08:30",
      available: true,
    },
    {
      time: "11:00",
      available: false,
    },
    {
      time: "14:00",
      available: true,
    },
    {
      time: "16:00",
      available: true,
    },
  ],
};

export const VALID_CUSTOMER_DETAILS = {
  fullName: "Jordan Lee",
  email: "jordan.lee@example.test",
  phone: "555-0134",
  notes: "Optional notes",
};
