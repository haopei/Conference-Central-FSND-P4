FSND P4: Conference Central
=====

### How to run

   1. Run `cd p4_conference_central`
   2. Start project on development server: `dev_appserver.py conference_central_complete`
   3. Visit `localhost:8080` to see website frontend. Create a few Conference entities, since these will be required for testing.
   4. Visit `localhost:8000` to see administration backend.
   5. Visit `localhost:8080/_ah/api/explorer` to visit the endpoints explorer page. Click 'conference API' to reveal a list of cloud endpoints.
   6. Create some Session entities using the `conference.createSession` endpoint, since these will be required for testing. Session inbound forms require the `parent_wsck` property — this is the parent websafe Conference key which can be retrieved in the datastore or the URL of a Conference page in the frontend.
   7. Visit any endpoint and test by entering the required body fields and clicking "Execute". To find the necessary websafe keys for the request body, refer to the datastore.


### Implementing Sessions and Speakers

  To implement the sessions feature, the `Sessions` ndb.Model is created, along with the following `protorpc.messages.Message` classes used for querying and returning endpoint responses:

  protorpc.messages.Message classes | Description
  --------------------------------- | -----------
  `SessionForm()`                   | Session outbound message
  `SessionForms()`                  | Multiple Session outbound messages
  `SessionByTypeQueryForm()`        | Used for querying Session by type. Takes 2 string parameters: session_type, and parent_wsck (urlsafe key of parent Conference entity.)
  `SessionBySpeakerQueryForm()`     | Used for querying Session by speaker. Takes 1 string parameter: speaker


   - The Session Kind contains the following properties: name (ndb.StringProperty), speakers (ndb.StringProperty), startTime (ndb.TimeProperty), duration (ndb.IntegerProperty), session_type(ndb.StringProperty), parent_wsck (ndb.StringProperty).
   - The Session's `speakers` is implemented as a list of strings, or `ndb.StringProperty(repeated=True)`; this allows one session to contain multiple speakers.
   - The Session's `startTime` uses a ndb.TimeProperty so that it can be used with equality or inequality operators.
   - Session's `parent_wsck` is a convenience property. Since `SessionForm(messages.Message)` is used for both inbound and outbound messages, it is convenient that `parent_wsck` exists on both SessionForm(messages.Message) and Session(ndb.Model) when `_copySessionToForm()` is used.
   - Both `SessionByTypeQueryForm()` and `SessionBySpeakerQueryForm()` require the minimal parameters to return the desired response.


### Two Additional Queries

  Two additional queries were created:

   - `getMostWishlistedSessions()`: returns the Session entity which is most wishlisted by users across all conferences. This may help users decide which sessions to not miss out on.

   - `getBusiestSpeaker()`: returns the speaker which appears most frequently across all Sessions entities, across all conferences. Perhaps a reward should be offered to this hard working person. Perhaps assign an assistant to make drinking water available to him at all times. He must be thirsty.


### Task 3: Handling multiple inequality queries of different properties

  The problem: NDB currently restricts multiple inequality queries across different properties. This means it is impossible to use a single query to find Sessions which start before 7pm (< inequality), and are not workshops (!= inequality).

  My solution in this project is implemented as the `doubleInequalityFilter()` endpoint method which makes two separate inequality queries. Subsequently, the common items between these two queries are then extracted using the _getMatchingItemsInList(list1, list2) function. The result is a list of sessions which are both 'non workshops' and occur before 7pm.

  Alternatively, possible solution is to make one of the two inequality queries (preferably the query which returns the fewer items), and then loop through the result set to further filter using the other inequality operator. For example, you may first query for all Sessions which start before 7PM. Then, loop through these sessions to only extract those which are not 'Workshop'.

  For larger data sets, Session(ndb.Model) may be remodelled to include a `startPeriod`, which indicates that a session may start during the ['morning', 'afternoon', 'evening']. This value may be computed using the `ndb.ComputedProperty`. For example, an event which occurs at 7PM will be computed to have a `startPeriod` value of 'evening'. Then, we may query for a significantly smaller result set: `Session.query(Session.startPeriod == 'evening').filter(Session.session_type != 'Workshop').fetch()`. Finally, we may loop through our smaller result set, and filter for those sessions where `session.startTime < 7PM`.



todo:
[] test queries on production

rubric:
[x] The README file includes an explanation about how sessions and speakers are implemented.
[x] Student response shows understanding of the process of data modeling and justifies their implementation decisions for the chosen data types.
[] can SessionBySpeakerQueryForm() use filterformat?
[x] The README file describes two additional query types that are consistent with the goals of the project.
[x] In the README, student describes the reason for the problem with the provided query.
[x] In the README, student proposes one or more solutions to the problematic query.
[] Code is ready for personal review and neatly formatted.
[x] The README file provides details of all the steps required to successfully run the application.

