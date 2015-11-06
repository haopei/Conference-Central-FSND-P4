FSND P4: Conference Central
=====

### How to Run

   1. Run `cd p4_conference_central` to change into the project directory
   2. Start project on development server: `dev_appserver.py conference_central_complete`
   3. Visit `localhost:8080` to see the website's frontend.
   4. Create a few Conference entities, since these will be required for testing.
   5. Visit `localhost:8000` to see administration backend, for accessing datastore, memcache and taskqueues.
   6. Visit `localhost:8080/_ah/api/explorer` for the endpoints explorer page. Click 'conference API' to reveal a list of cloud endpoints.
   7. Create some Session entities using the `conference.createSession` endpoint; these will be required for testing. The SessionForm() inbound form (for creating session entities) require the `parent_wsck` property — this is the 'parent websafe conference key' which can be retrieved from the datastore or the URL of a Conference page in the frontend.
   8. Visit any endpoint and test by entering the required body fields and clicking "Execute". To find the necessary websafe keys for the request body, refer to the datastore.


### Implementing Sessions and Speakers

  To implement the sessions feature, `Sessions(ndb.Model)` is created, along with the following inbound/outbound forms used for querying and returning endpoint responses:

  protorpc.messages.Message classes | Description
  --------------------------------- | -----------
   SessionForm()                    | Session inbound/outbound message
   SessionForms()                   | Multiple Session outbound messages
   SessionByTypeQueryForm()         | Used for querying Session entities by type. Takes 2 string parameters: `session_type`, and `parent_wsck`.
   SessionBySpeakerQueryForm()      | Used for querying Session by speaker. Takes 1 string parameter: `speaker`


   - The Session Kind contains the following properties: `name(ndb.StringProperty)`, `speakers(ndb.StringProperty)`, `startTime(ndb.TimeProperty)`, `duration(ndb.IntegerProperty)`, `session_type(ndb.StringProperty)`, `parent_wsck(ndb.StringProperty)`.
   - The Session's `speakers` property is implemented as a list of strings, or `ndb.StringProperty(repeated=True)`; this allows a session to contain multiple speakers.
   - The Session's `startTime` uses a `ndb.TimeProperty` so that it can be used with equality/inequality operators.
   - The Session's `parent_wsck` is a convenience property. Since `SessionForm(messages.Message)` is used for both inbound and outbound messages, it is convenient that `parent_wsck` exists on both `SessionForm(messages.Message)` and `Session(ndb.Model)` when `_copySessionToForm()` is used.
   - Both `SessionByTypeQueryForm()` and `SessionBySpeakerQueryForm()` were created to simplify querying, since they require the minimal parameters to return the desired response.


### Two Additional Queries

  Two additional queries were created:

   - `getMostWishlistedSessions()`: returns the Session entity which is most wishlisted by users across all conferences. This may help users decide which sessions to not miss out on.

   - `getBusiestSpeaker()`: returns the speaker who appears most frequently across all sessions and conferences. Perhaps a reward should be offered to this hard working person, or at least an someone assigned to him, making water available to him at all times. He must be thirsty.


### Task 3: Handling multiple inequality queries of different properties

  ##### The Problem

  NDB currently restricts multiple inequality queries of different properties.

  ##### My Solution

  My solution in this project is implemented as the `doubleInequalityFilter()` endpoint method which makes two separate inequality queries (one which finds Session entities which are not 'Workshop', and another which finds Session entities which start before 7PM). Both queries use `keys_only=True` to return a smaller sized result. Subsequently, the common entities between these two queries are then retrieved using `ndb.get_multi(set(first_list_of_keys))intersection(second_list_of_keys))`. The result is a list of sessions which are both 'non workshops' and occur before 7pm.

  ##### Alternative Solution

  An alternative solution is to make just one of the two inequality queries (preferably the query which is expected to return fewer items), and then loop through the result set to further filter using the other inequality operator. For example, you may first query for all Sessions which start before 7PM. Then, loop through these sessions to only extract those which are not 'Workshop'.

  ##### Handling Larger Results

  For larger data sets, `Session(ndb.Model)` may be remodelled to include a `startPeriod` property, which indicates that a session may start either in the `morning` (6AM-12PM), `afternoon` (1PM-6PM), or `evening` (6PM-11AM). This value may be computed using the `ndb.ComputedProperty()`. For example, an event which occurs at 7PM will be computed to have a `startPeriod` value of 'evening'. Then, we may query for a significantly smaller result set: `Session.query(Session.startPeriod == 'evening').filter(Session.session_type != 'Workshop').fetch()`. Finally, we may loop through our smaller result set, and filter for those sessions where `session.startTime < 7PM`.
