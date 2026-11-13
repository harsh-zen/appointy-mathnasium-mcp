"""Allowlisted read queries verified with API-key-only QA requests. No raw query tool."""

COMPANY_METADATA = 'query SupportRead($c:ID){company(id:$c,viewMask:{paths:["id","metadata","created_on","updated_on"]}){id metadata createdOn updatedOn}}'

BOOKING_RULES = "query SupportRead($p:String){serviceSetting(parent:$p){id changeMask{paths} bookingRules{availabilityType fixedInterval precisionPattern leadAndCancellationSetting{minAdvancePeriodToBookAppointment minAdvancePeriodToCancelAppointment minAdvancePeriodToRescheduleAppointment timeAdvanceAppointmentCanBeBooked minAdvanceIntervalToBook{cutOff interval{count frequency}} intervalAdvanceAppointmentCanBeBooked{count frequency} forCancellation{policyType minAdvanceInterval{cutOff interval{count frequency}}} forRescheduling{policyType minAdvanceInterval{cutOff interval{count frequency}}}}}}}"

PORTAL_SETTINGS = "query SupportRead($p:String){appointmentBookingFlowSetting(parent:$p){id allowBookingFromBookingPortal allowRecurringBookingAdmin allowRecurringBookingCustomer doNotAllowBookingIfOpenHourNotAvailable} bookingPortalSetting(parent:$p){id enableBookingPortal enabledLogins changeMask{paths}} customerSetting(parent:$p){id bookingType customizations{name enable}}}"

AVAILABILITY_WINDOW = "query SupportRead($p:[String],$start:Timestamp,$end:Timestamp){listOpenHourRulesForAvailability(parents:$p,startTime:$start,endTime:$end,fetchActiveOnly:false){openHours{id resourceId timezone openHour{id start until capacity recurrenceSet serviceIds slot{startTime endTime}}}}}"

BOOKABLE_SLOTS = "query SupportRead($f:[MathnasiumFilterInput],$tz:String){mathnasiumServicesOrEmployees(filters:$f,listEmployees:false,skipValidations:false){nodes{studentId availableIds errorMessage}} mathnasiumAvailability(filters:$f,skipValidations:false,timezone:$tz){nodes{studentId errorMessage slots{slotType slot{capacity service employee enrolmentId timeSlot{startTime endTime}}}}}}"

ENROLLMENT_BALANCE = "query SupportRead($s:String,$g:String,$tz:String){studentsRemainingSessions(studentId:$s,guardianId:$g,timezone:$tz){enrolmentRemainingSessions{enrolmentId enrolmentType remainingSessions{startDate endDate remainingSessions isUnlimited}} restrictionsRemainingSessions{frequency remainingSessions{startDate endDate remainingSessions isUnlimited}}}}"

RECURRING_SERIES = "query SupportRead($a:String){getRecurringAppointmentSeries(appointmentId:$a){recurrenceSet seriesAppointments{appointment{id recurringId timeSlot{startTime endTime}} isUpdated}}}"

ATTENDANCE_STATUSES = "query SupportRead($p:String){appointmentCustomStatuses(parent:$p,fetchBelowLevel:true){customStatus{id name}}}"

GUARDIAN_PROFILE = "query SupportRead($g:ID){customer(id:$g,accessContact:true){id timezone userProfileTimezone createdOn updatedOn}}"

STUDENT_SEARCH = "query SupportRead($g:String,$q:String){mathnasiumSearchEntity(groupId:$g,query:$q,type:Student){encodedData}}"

RADIUS_STUDENT = "query SupportRead($g:String,$s:String){mathnasiumStudentWithEnrolment(groupId:$g,studentId:$s){student{appointyId studentId organizationId enrolments{appointyId enrolmentId remainingSessions maxSessions startDateTime terminationDateTime}}}}"

BOOKABLE_DURATIONS = "query SupportRead($p:String,$s:String,$v:String,$slot:TimeslotInput){studentBookableDurations(parent:$p,studentId:$s,serviceId:$v,timeSlot:$slot){bookableDurations}}"

CONSUMER_COUNT = "query SupportRead($p:String,$s:String){consumerAppointmentCount(parent:$p,consumerId:$s){consumerId count}}"

AVAILABILITY_RULES = "query SupportRead($p:String,$n:Int,$a:String){openHourRules(parent:$p,first:$n,after:$a,filter:{fetchActiveOnly:false}){edges{node{id resourceId openHourType timezone metadata openHour{id start until slot{startTime endTime} capacity serviceIds recurrenceSet exceptions{id date exceptionDeleted}}}}pageInfo{hasNextPage endCursor}}}"

STUDENT_AUDIT = 'query SupportRead($id:ID){student(id:$id,viewMask:{paths:["id","created_on","updated_on","created_by","updated_by"]}){id createdOn updatedOn createdBy updatedBy}}'

RECORD_METADATA = 'query SupportRead($c:ID,$l:ID){company(id:$c,viewMask:{paths:["id","metadata","created_on","updated_on"]}){id metadata createdOn updatedOn} location(id:$l){id metadata createdOn updatedOn}}'

INSTRUCTOR_SERVICES = "query SupportRead($e:String,$l:String,$n:Int,$a:String){listServicesOfEmployee(employeeId:$e,locationId:$l,first:$n,after:$a){edges{node{id title}}pageInfo{hasNextPage endCursor}}}"

ACTIVITY_LOGS = "query SupportRead($p:[String],$n:Int,$o:Int,$filter:ListActivityLogFilterInput){activityLogs(parents:$p,limit:$n,offset:$o,filter:$filter){totalCount edges{node{id createdOn userId activityLogData displayEventName activityId}}pageInfo{hasNextPage nextOffset}}}"

APPOINTMENTS = "query SupportRead($p:String,$c:listAppointmentRequestConsumerId,$g:String,$slot:TimeslotInput,$after:String,$n:Int,$status:AppointmentStatusFilterInput,$order:OrderBy){appointments(parent:$p,consumerId:$c,customerId:$g,timeslot:$slot,first:$n,after:$after,status:$status,sortBy:StartTime,orderBy:$order){edges{cursor node{id status booked_by booked_on isBookedByAdmin updatedOn updatedBy recurringId recurrenceSet lastStatusUpdatedOn lastStatusUpdatedBy isLastStatusUpdatedByAdmin timeSlot{startTime endTime} service{_id title} employee{_id name} consumers{_id bookingCustomerId consumerType status timezone customStatus{customStatusId customStatusName} customStatusLastChangedOn cancelationReason} historicalData{createdOn createdBy isCreatedByAdmin status message consumerIds}}}pageInfo{hasNextPage endCursor}}}"

COMPANY_CONTEXT = 'query SupportRead($id:ID){company(id:$id){id title displayName customCompanyId active metadata preference{timezone currency language dateFormat timeFormat} companySettings{id aliases(locale:"en-US") customization{disableApps disableStaffBooking}} apps{id name active appTypeId} slugObject{slugValue}}}'

LOCATION_CONTEXT = "query SupportRead($id:ID){location(id:$id){id name customLocationId active metadata preference{timezone currency language dateFormat timeFormat} slugObject{slugValue} address{country locality postalCode region streetAddress} telephones}}"

STUDENT_TIMESTAMPS = 'query SupportRead($id:ID){student(id:$id,viewMask:{paths:["id","created_on","updated_on"]}){id createdOn updatedOn}}'
