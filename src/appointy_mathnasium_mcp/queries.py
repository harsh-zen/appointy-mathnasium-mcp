from typing import Dict, Tuple

GRAPHQL_APP_QUERY = """
query AppQuery {
  viewer {
    id
    groups {
      id
      name
      groupSettings {
        id
        adminCss
        metadata
        hasExtendedFields
      }
      companies {
        id
        title
        displayName
        profession
        active
        customCompanyId
        preference {
          currency
          dateFormat
          language
          timeFormat
          timezone
          uiInfo
          id
        }
        metadata
        address {
          country
          latitude
          locality
          longitude
          postalCode
          region
          streetAddress
        }
        slugObject {
          id
          slugType
          slugValue
        }
        companySettings {
          id
          navMenus
          aliases(locale: "en-US")
          customization {
            disableApps
            disableStaffBooking
          }
        }
        roleLevelCustomization {
          disableApps
          readonlyApps
          id
        }
        apps {
          id
          appTypeId
          name
          active
          serviceModules
        }
        locations(first: 500) {
          edges {
            node {
              id
              name
              customLocationId
              active
              preference {
                currency
                dateFormat
                language
                timeFormat
                timezone
                uiInfo
                id
              }
              slugObject {
                id
                slugType
                slugValue
              }
              address {
                country
                latitude
                locality
                longitude
                postalCode
                region
                streetAddress
              }
              telephones
              description
              metadata
            }
          }
        }
      }
    }
  }
}
""".strip()

GRAPHQL_FIND_GUARDIANS_QUERY = """
query FindGuardianQuery(
  $parent: String!
  $first: Int!
  $firstName: String
  $email: String
  $phone: String
  $locationIds: [String!]
) {
  customers(
    parent: $parent
    first: $first
    firstName: $firstName
    email: $email
    phoneNumber: $phone
    locationIds: $locationIds
    accessContact: true
  ) {
    edges {
      node {
        id
        firstName
        lastName
        email
        phoneNumber
        customCustomerId
        metadata
      }
    }
  }
}
""".strip()

GRAPHQL_GUARDIAN_DETAIL_QUERY = """
query CustomerDetailQuery($customerId: String) {
  students(guardianId: { guardianId: $customerId }, first: 100) {
    edges {
      node {
        id
        firstName
        lastName
        email
        grade
        customStudentId
        metadata
        primaryGuardianId
        studentLocationsLink {
          locationIds
          studentId
        }
        enrolments {
          id
          customEnrolmentId
          customStudentId
          enrolmentBaseType
          gradeRangeId
          maxSessions
          remainingSessions
          membershipTypeId
          sessionLengths
          startDate
          terminationDate
          studentId
          deliveryMethods {
            deliveryMethod
            timeSlot {
              startTime
              endTime
            }
          }
          holds {
            id
            customHoldId
            deleteScheduledSessions
            startDate
            endDate
          }
        }
      }
    }
  }
  customerLocationLinks(customerId: $customerId) {
    locationIds
  }
}
""".strip()

GRAPHQL_FIND_STUDENTS_QUERY = """
query FindStudentQuery(
  $parent: String!
  $first: Int!
  $query: String
  $guardianId: String
) {
  students(
    parent: { parent: $parent }
    first: $first
    query: $query
    guardianId: { guardianId: $guardianId }
  ) {
    edges {
      node {
        id
        firstName
        lastName
        email
        grade
        customStudentId
        metadata
        primaryGuardianId
        studentLocationsLink {
          locationIds
          studentId
        }
        enrolments {
          id
          customEnrolmentId
          customStudentId
          enrolmentBaseType
          gradeRangeId
          maxSessions
          remainingSessions
          membershipTypeId
          sessionLengths
          startDate
          terminationDate
          studentId
          deliveryMethods {
            deliveryMethod
            timeSlot {
              startTime
              endTime
            }
          }
          holds {
            id
            customHoldId
            deleteScheduledSessions
            startDate
            endDate
          }
        }
      }
    }
  }
}
""".strip()

GRAPHQL_FIND_STUDENTS_QUERY_NO_GUARDIAN = """
query FindStudentQuery(
  $parent: String!
  $first: Int!
  $query: String
) {
  students(
    parent: { parent: $parent }
    first: $first
    query: $query
  ) {
    edges {
      node {
        id
        firstName
        lastName
        email
        grade
        customStudentId
        metadata
        primaryGuardianId
        studentLocationsLink {
          locationIds
          studentId
        }
        enrolments {
          id
          customEnrolmentId
          customStudentId
          enrolmentBaseType
          gradeRangeId
          maxSessions
          remainingSessions
          membershipTypeId
          sessionLengths
          startDate
          terminationDate
          studentId
          deliveryMethods {
            deliveryMethod
            timeSlot {
              startTime
              endTime
            }
          }
          holds {
            id
            customHoldId
            deleteScheduledSessions
            startDate
            endDate
          }
        }
      }
    }
  }
}
""".strip()

GRAPHQL_STUDENT_DETAIL_QUERY = """
query StudentDetailQuery($id: ID!) {
  student(id: $id) {
    id
    firstName
    lastName
    email
    grade
    customStudentId
    metadata
    primaryGuardianId
    studentLocationsLink {
      locationIds
      studentId
    }
    enrolments {
      id
      customEnrolmentId
      customStudentId
      enrolmentBaseType
      gradeRangeId
      maxSessions
      remainingSessions
      membershipTypeId
      sessionLengths
      startDate
      terminationDate
      studentId
      deliveryMethods {
        deliveryMethod
        timeSlot {
          startTime
          endTime
        }
      }
      holds {
        id
        customHoldId
        deleteScheduledSessions
        startDate
        endDate
      }
    }
  }
}
""".strip()

GRAPHQL_OTHER_ENTITY_QUERIES: Dict[str, Tuple[str, str, str]] = {
    "appointments": (
        "MathnasiumEntityAppointmentsQuery",
        "appointments",
        """
query MathnasiumEntityAppointmentsQuery($parent: String!, $first: Int!) {
  appointments(parent: $parent, first: $first) {
    edges {
      node {
        id
        status
        paymentStatus
        timeSlot {
          startTime
          endTime
        }
      }
    }
  }
}
""".strip(),
    ),
    "services": (
        "MathnasiumEntityServicesQuery",
        "services",
        """
query MathnasiumEntityServicesQuery($parent: String!, $first: Int!) {
  services(parent: $parent, first: $first) {
    edges {
      node {
        id
        title
        description
        active
        status
        serviceType
        capacity
        durations
        mathnasiumServiceLinks {
          id
          locationId
          serviceId
          memberships {
            id
            name
          }
          grades {
            id
            name
          }
        }
        settings {
          id
          bookingRules {
            availabilityType
            detectCustomerTimezone
            fixedInterval
            precisionPattern
          }
        }
      }
    }
  }
}
""".strip(),
    ),
    "employees": (
        "MathnasiumEntityEmployeesQuery",
        "employees",
        """
query MathnasiumEntityEmployeesQuery($parent: String!, $first: Int!) {
  employees(parent: $parent, first: $first) {
    edges {
      node {
        id
        firstName
        lastName
        email
        phoneNumber
        active
      }
    }
  }
}
""".strip(),
    ),
    "resources": (
        "MathnasiumEntityResourcesQuery",
        "resources",
        """
query MathnasiumEntityResourcesQuery($parent: String!, $first: Int!) {
  resources(parent: $parent, first: $first) {
    edges {
      node {
        id
        title
        description
        active
      }
    }
  }
}
""".strip(),
    ),
}
