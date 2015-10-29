The project
***********

    Rubric: https://docs.google.com/document/d/1lVFoZDY-jjg6SoI8g5uZ72V3TDp7iLTz2UGWAI5ZvfE/edit#heading=h.ey3q6ofsnobh

    Course Docs: https://docs.google.com/document/d/1H9anIDV4QCPttiQEwpGe6MnMBx92XCOlz0B4ciD7lOs/pub

    Develop a cloud based API server for a provided 'conference organisation' app that exists on the web. These functions must be found:
        [] user authentication
        [] user profiles
        [] conference information
        [] various manners in which to query data


Notes
*****

    - Some conferences have sessions by different speakers, types (workshops, lectures, etc), names, and some sessions may be happening in parallel.
    - Explain in a couple of paragraphs your design choices for session and speaker implementation.


Additional Components
*********************
    [] Sessions
    [] Wishlist
    [] Two additional queries + solve query problem
    [] Add Task and use Memcache
    [] Define getFeaturedSpeaker() endpoint method

How to complete project
***********************

    0.  Must submit app id and texts for parts of the project that require explanation

    1. No need to work on front end of project; all functionality will be tested via API explorer.
    2. Clone repository (https://github.com/udacity/ud858)
    3. Add Sessions to a Conference.
        a. Define the following endpoints:
            [] getConferenceSessions(websafeConferenceKey) -- given a conference, return all sessions
            [] getConferenceSessionsByType(websafeConferenceKey, typeOfSession) - Given a conference, return all sessions of a specific type (eg. lecture, keynote, workshop)
            [] getSessionsBySpeaker(speaker) -- Given a speaker, return all sessions given by this particular speaker, across all conferences
            [] createSession(SessionForm, websafeConferenceKey) -- open to the organizer of the conference
        b. Define Session class and SessionForm
            - Session name
            - highlights
            - speaker
            - duration
            - typeOfSession
            - date
            - start time (in 24 hour notation so it can be ordered).

    4. Add Sessions to User Wishlist. Define the following Endpoints methods
        - addSessionToWishlist(SessionKey) -- adds the session to the user's list of sessions they are interested in attending
        - getSessionsInWishlist() -- query for all the sessions in a conference that the user is interested in

    5. Work on indexes and queries
        - Create indexes
        - Come up with 2 additional queries
        - Solve the following query related problem: Let’s say that you don't like workshops and you don't like sessions after 7 pm. How would you handle a query for all non-workshop sessions before 7 pm? What is the problem for implementing this query? What ways to solve it did you think of?

    6. Add a Task
        - When adding a new session to a conference, determine whether or not the session's speaker should be the new featured speaker. This should be handled using App Engine's Task Queue.
        - Define the following endpoints method: getFeaturedSpeaker()
