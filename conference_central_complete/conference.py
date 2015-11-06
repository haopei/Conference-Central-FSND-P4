#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import endpoints
from protorpc import messages, message_types, remote

from google.appengine.api import memcache, taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import BooleanMessage
from models import StringMessage

from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize

from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms

from models import Session
from models import SessionForm
from models import SessionForms
from models import SessionQueryForm
from models import SessionQueryForms
from models import SessionByTypeQueryForm
from models import SessionBySpeakerQueryForm

from models import SessionWishlistItem
from models import SessionWishlistItemForm
from models import SessionWishlistQueryForm
# from models import SessionWishlist
# from models import SessionWishlistForm
# from models import SessionWishlistQueryForm

from settings import WEB_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID, ANDROID_AUDIENCE

from utils import getUserId
from datetime import datetime
from collections import Counter

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

CONF_GET_REQUEST = endpoints.ResourceContainer(message_types.VoidMessage, websafeConferenceKey=messages.StringField(1),)
CONF_POST_REQUEST = endpoints.ResourceContainer(ConferenceForm, websafeConferenceKey=messages.StringField(1),)

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"]}
FIELDS = {
    'CITY': 'city',
    'TOPIC': 'topics',
    'MONTH': 'month',
    'MAX_ATTENDEES': 'maxAttendees'}
OPERATORS = {
    'EQ':   '=',
    'GT':   '>',
    'GTEQ': '>=',
    'LT':   '<',
    'LTEQ': '<=',
    'NE':   '!='}

MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')

@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE], allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID], scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

    def _getCurrentUser(self):
        """gets the current logged in user's username; to be replaced by _getCurrentUserProfile()"""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        return user

    def _getCurrentUserProfile(self):
        """gets the current logged in user's Profile entity"""
        username = endpoints.get_current_user()
        if not username:
            raise endpoints.UnauthorizedException('User is not logged in.')

        user_id = getUserId(username)
        if not user_id:
            raise endpoints.NotFoundException('user_id cannot be retrieved from username: %s' % username)

        user_profile = ndb.Key(Profile, user_id).get()
        if not user_profile:
            raise endpoints.NotFoundException('Cannot find Profile from user_id: %s' % user_id)

        return user_profile

    def _getEntityByWebSafeKey(self, websafe_key):
        """Given a websafe key, return parent Conference entity entity"""
        parent_entity = ndb.Key(urlsafe=websafe_key).get()
        if not parent_entity:
            raise endpoints.NotFoundException(
                'No parent entity found by this websafe key: %s' % websafe_key)
        return parent_entity

# - - - Conferences - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = self._getCurrentUser()
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(), 'conferenceInfo': repr(request)}, url='/tasks/send_confirmation_email')
        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = self._getCurrentUser()
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(ConferenceForm, ConferenceForm, path='conference', http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm, path='conference/{websafeConferenceKey}', http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(CONF_GET_REQUEST, ConferenceForm, path='conference/{websafeConferenceKey}', http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(message_types.VoidMessage, ConferenceForms, path='getConferencesCreated', http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""

        user = self._getCurrentUser()
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, getattr(prof, 'displayName')) for conf in confs]
        )

    def _getQuery(self, request, kind="Conference"):
        """Return formatted query from the submitted filters.
           The request (ConferenceQueryForms) from queryConferences is passed here.
           The request.filters is passed to _formatFilters(request.filters)
           The filters are a list of ConferenceQueryForms
        """

        q = Conference.query()

        # request is ConferenceQueryForms
        # request.filter is list of ConferenceQueryForm
        #   because ConferenceQueryForm is contained within ConferenceQueryForms
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
            # print '_getQuery returns: %s' % q

        # example returns: Query(kind='Conference', filters=FilterNode('city', '>', u'San Francisco'), orders=...)
        return q

    # FIELDS = {
    #     'CITY': 'city',
    #     'TOPIC': 'topics',
    #     'MONTH': 'month',
    #     'MAX_ATTENDEES': 'maxAttendees'}

    # OPERATORS = {
    #     'EQ':   '=',
    #     'GT':   '>',
    #     'GTEQ': '>=',
    #     'LT':   '<',
    #     'LTEQ': '<=',
    #     'NE':   '!='}

    def _formatFilters(self, filters):
        """ Parse, check validity and format user supplied filters.
            The request (ConferenceQueryForms) from queryConferences to _getQuery(request).
            _getQuery then passes request.filters (ConferenceQueryForm)
            The request.filters is a list of ConferenceQueryForms
        """

        # filters is a list of ConferenceQueryForm
        formatted_filters = []
        inequality_field = None

        # transform ConferenceQueryForm into dictionary
        # example, turns this: [<ConferenceQueryForm field: u'CITY' operator: u'EQ' value: u'San Francisco'>]
        # into this: {'value': u'San Francisco', 'field': u'CITY', 'operator': u'EQ'}
        for f in filters:
            # filtr is the dict format of ConferenceQueryForms
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]
            formatted_filters.append(filtr)
        result = (inequality_field, formatted_filters)

        #example returns: ('city', [{'field': 'city', 'value': u'San Francisco', 'operator': '>'}, {'field': 'topics', 'value': u'Web', 'operator': '='}])
        return result

    @endpoints.method(ConferenceQueryForms, ConferenceForms, path='queryConferences', http_method='POST', name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""

        # getQuery returns: Query(kind='Conference', filters=FilterNode('city', '>', u'San Francisco'), orders=...)
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = dict()
        for profile in profiles:
            names[profile.key.id()] = profile.displayName or None

        # return individual ConferenceForm object per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in conferences])

# - - - Profile - - - - - - - - - - - - - - - - - - -
    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        user = self._getCurrentUser()

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()

        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),)
            profile.put()
        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        # save_request is in ProfileMiniForm form
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        #if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        #else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(message_types.VoidMessage, ProfileForm, path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm, path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)

# - - - Announcements - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage, path='conference/announcement/get', http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")

# - - - Conference Registration - - - - - - - - - - -
    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        # retrieve conference entity using websafe key
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(message_types.VoidMessage, ConferenceForms, path='conferences/attending', http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile

        # build ndb.Keys() using the websafe keys inside prof.conferenceKeysToAttend
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers (users who create confs)
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in conferences])

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage, path='conference/{websafeConferenceKey}', http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(CONF_GET_REQUEST, BooleanMessage, path='conference/{websafeConferenceKey}', http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)

# - - - Sessions - - - - - - - - - - - - - - - - - - -

    def _copySessionToForm(self, session):
        """Copy relevant fields from Session (SessionForm) to SessionForm"""
        sf = SessionForm()
        for field in sf.all_fields():
            # check session container to see if matching fields exist
            if hasattr(session, field.name):
                # convert time fields to string; just copy others
                if field.name.endswith('Time'):
                    setattr(sf, field.name, getattr(session, field.name).strftime("%I"))
                else:
                    # set session container's matching field's value to that of SessionForm()
                    val_to_set = getattr(session, field.name)
                    setattr(sf, field.name, val_to_set)  # setattr(x, 'foobar', 123) is equivalent to x.foobar = 123
        sf.check_initialized()
        return sf

    @staticmethod
    def _checkFeaturedSpeaker(wsck):
        """Check to see if a speaker is in more than one sessions in a conference"""

        # get the session's parent conference
        conference = ndb.Key(urlsafe=wsck).get()

        # find sessions in this conference
        sessions = Session.query(ancestor=conference.key).fetch()

        # retrieve all speakers from all sessions in this Conference
        all_sessions_speakers = list()
        for sess in sessions:
            all_sessions_speakers.extend(sess.speakers)

        # add featured speaker to memecache
        if all_sessions_speakers:
            # get the most frequently occuring speaker's name from the list of all speakers
            featured_speaker = max(set(all_sessions_speakers), key=all_sessions_speakers.count)
            data = "Today's featured speaker is %s" % str(featured_speaker)

            # update memcache entry for featured_speaker
            memcache.delete('featured_speaker')
            memcache.add("featured_speaker", data)
        return

    def _createSessionObject(self, request):

        # get current user
        # returns a Profile object
        user = self._getCurrentUser()

        # get parent Conference entity using wsck from request
        parent_conf = self._getEntityByWebSafeKey(request.parent_wsck)

        # Allocate id for new Session entity
        session_id = Session.allocate_ids(size=1, parent=parent_conf.key)[0]
        session_key = ndb.Key(Session, session_id, parent=parent_conf.key)

        # add values to data from request object (SessionForm)
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # convert startTime into datetime.time object
        #   since Session Kind expects a ndb.TimeProperty
        data['startTime'] = datetime.strptime(data['startTime'], '%H').time()

        # assign the key of the to-be-created Session entity to be the session_key,
        #   which has the parent_conf embedded as the parent.
        data['key'] = session_key

        # create the session entity
        Session(**data).put()

        # create a task to update the featured speaker, if required.
        taskqueue.add(url="/tasks/check_featured_speaker", params={'conference': request.parent_wsck})

        return request

    # TASK 1: COMPLETE
    @endpoints.method(SessionForm, SessionForm, path='createSession', http_method='POST', name='createSession')
    def createSession(self, request):
        """Create a Session entity given a parent wsck"""
        # TODO: only the creator of the conference can create its child sessions
        return self._createSessionObject(request)

    # TASK 2: COMPLETE
    @endpoints.method(SessionForm, SessionForms, path='getConferenceSessions', http_method='POST', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Given a conference, return its sessions"""

        # get the parent conference entity using the request.wsck
        parent_conf = self._getEntityByWebSafeKey(request.parent_wsck)

        # query sessions using the parent_conf as ancestor
        sessions = Session.query(ancestor=parent_conf.key).fetch()

        return SessionForms(items=[self._copySessionToForm(session) for session in sessions])

    # TASK 3: COMPLETE
    @endpoints.method(SessionByTypeQueryForm, SessionForms, path='getConferenceSessionsByType', http_method='POST', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Given a conference, return all sessions of a specified type (eg lecture, keynote, workshop)"""

        parent_conf = self._getEntityByWebSafeKey(request.parent_wsck)
        sessions = Session.query(ancestor=parent_conf.key).filter(Session.session_type == request.session_type)

        return SessionForms(items=[self._copySessionToForm(session) for session in sessions])

    # TASK 4: COMPLETE
    @endpoints.method(SessionBySpeakerQueryForm, SessionForms, path='getSessionsBySpeaker', http_method='POST', name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """Returns all sessions given a particular speaker"""
        sessions = Session.query().filter(Session.speakers.IN([request.speaker]))

        return SessionForms(items=[self._copySessionToForm(session) for session in sessions])

# - - - Wishlist - - - - - - - - - - - - - - - - - - -

    @endpoints.method(SessionWishlistItemForm, SessionWishlistItemForm, path='addSessionToWishlist', http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Add session to user's wishlist, given a session"""

        # get current user
        user = self._getCurrentUserProfile()

        # retrieve Session entity from request to be added to wishlist
        session_websafe_key = request.session_websafe_key
        session_to_add = self._getEntityByWebSafeKey(session_websafe_key)

        # check if user already added this Session to wishlist
        session_in_wishlist = SessionWishlistItem.query(ancestor=user.key).filter(SessionWishlistItem.session_websafe_key == session_websafe_key).get()
        if session_in_wishlist:
            raise ConflictException('Session already found in wishlist.')

        # define SessionWishlistItem id allocation and key
        #   with user.key as parent
        session_wishlist_id = SessionWishlistItem.allocate_ids(size=1, parent=user.key)[0]
        session_wishlist_key = ndb.Key(SessionWishlistItem, session_wishlist_id, parent=user.key)

        # prepare data to be used for creating new wishlist item
        data = dict()
        data['key'] = session_wishlist_key  # overwrite automatically generated key with our custom parental key
        data['session_websafe_key'] = session_websafe_key
        data['parent_wsck'] = session_to_add.parent_wsck
        SessionWishlistItem(**data).put()

        return request

    # COMPLETE
    @endpoints.method(SessionWishlistQueryForm, SessionForms, path='getSessionsInWishlist', http_method='POST', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Query for all the sessions in a conference that the user is interested in
            Given any user and conference, find all SessionWishlistItem in that session
        """

        # get user and conference from request
        user = self._getEntityByWebSafeKey(request.user_websafe_key)
        conference = self._getEntityByWebSafeKey(request.wsck)

        # query for SessionWishlistItem entities
        #   given user as ancestor
        #   and wsck as parent conference
        wishlist = SessionWishlistItem.query(
            ancestor=user.key).filter(
            SessionWishlistItem.parent_wsck == conference.key.urlsafe()).fetch()

        # get Session entities from wishlist
        sessions = [ndb.Key(urlsafe=wishlist_item.session_websafe_key).get() for wishlist_item in wishlist]

        return SessionForms(items=[self._copySessionToForm(session) for session in sessions])

# - - - Get Featured Speaker - - - - - - - - - - - - - - -

    @endpoints.method(message_types.VoidMessage, StringMessage, path='getFeaturedSpeaker', http_method='POST', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Retrieve the featured speaker from memcache"""
        featured_speaker = memcache.get('featured_speaker')
        if not featured_speaker:
            featured_speaker = "No featured speaker right now."

        return StringMessage(data=featured_speaker)

# - - - Playground - - - - - - - - - - - - - - - - - - -
    @endpoints.method(message_types.VoidMessage, ConferenceForms, path='filterPlayground', http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""

        # parent_conf = self._getEntityByWebSafeKey("ah5kZXZ-Y29uZmVyZW5jZS1jZW50cmFsLWZzbmQtcDRyMQsSB1Byb2ZpbGUiFGhhb3BlaXlhbmdAZ21haWwuY29tDAsSCkNvbmZlcmVuY2UYJAw")
        # q = self._getSessionQuery(request)

        # field = "city"
        # operator = "="
        # value = "Paris"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)

        # q = Conference.query()
        # q = q.filter(Conference.city == "San Francisco")
        # q = q.filter(Conference.topics == "Programming Languages")
        # q = q.order(Conference.name)
        # q = q.filter(Conference.month == 6)

        time_7_pm = datetime.strptime('19', '%H').time()

        results = Session.query(Session.startTime > time_7_pm).fetch()

        print results
        print ''

        new_results = list()
        for r in results:
            if r.session_type != "Workshop":
                new_results.append(r)

        print new_results
        # print ''
        # print results
        # print ''

        # return ConferenceForms(items=[self._copyConferenceToForm(conf, "") for conf in q])
        return ConferenceForms(items=[])

# - - - Additional Queries - - - - - - - - - - - - - - - - -

    def _mostCommonItem(self, lst):
        """Returns the most frequently occuring item in a list"""
        return max(set(lst), key=lst.count)

    # 1. Most wishlisted for session
    @endpoints.method(message_types.VoidMessage, SessionForm, path='mostWishlistedSessions', http_method='POST', name='mostWishlistedSessions')
    def mostWishlistedSessions(self, request):
        """Returns the most wishlisted session"""
        wishlisted_sessions = SessionWishlistItem.query().fetch()

        # extract session keys
        #   to be used for the _mostCommonItem(session_keys) which uses set()
        #   and 'Model' is not immutable
        session_keys = [sess.session_websafe_key for sess in wishlisted_sessions]

        # get most common item in list (the most frequently wishlisted session)
        most_wishlisted_session = ndb.Key(urlsafe=self._mostCommonItem(session_keys)).get()

        return self._copySessionToForm(most_wishlisted_session)

    # 2. Most registered session
    @endpoints.method(message_types.VoidMessage, StringMessage, path='BusiestSpeaker', http_method='POST', name='BusiestSpeaker')
    def BusiestSpeaker(self, request):
        """Return the businest speaker who speaks at the most sessions across all conferences"""

        # get all sessions
        all_sessions = Session.query().fetch()

        # extract a list of lists of speakers from all sessions
        list_of_lists_of_speakers = [sess.speakers for sess in all_sessions]

        # merge all speakers in one flat list
        all_speakers = list()
        for speakers in list_of_lists_of_speakers:
            all_speakers.extend(speakers)

        # get busiest speaker
        busiest_speaker = self._mostCommonItem(all_speakers)

        response = "The businest speaker across all sessions is %s." % busiest_speaker

        return StringMessage(data=response)

    # 3. Non-workshop, before 7PM

    def _getMatchingItemsInList(self, list1, list2):
        """Returns common items in two lists."""
        return [i for i in list1 if i in list2]

    @endpoints.method(message_types.VoidMessage, SessionForms, path='doubleInequalityFilter', http_method='POST', name='doubleInequalityFilter')
    def doubleInequalityFilter(self, request):
        """ Handling queries with multiple inequality filters
            Queries for non-workshop sessions before 7PM """

        """
            App engine does not allow multiple inequality filters on different properties.
            So, one way around this is to first perform an inequality filter for just one property.
            Then, use a loop to filter the second inequality filter."""

        # firstly, query for non-workshop sessions
        time_seven_pm = datetime.strptime('19', '%H').time()
        non_workshop_sessions = Session.query(Session.session_type != 'Workshop').fetch()
        before_seven_pm_sessions = Session.query(Session.startTime < time_seven_pm).fetch()

        # return matching entities in both list of sessions
        filtered_sessions = self._getMatchingItemsInList(non_workshop_sessions, before_seven_pm_sessions)

        return SessionForms(items=[self._copySessionToForm(sess) for sess in filtered_sessions])

# register API
api = endpoints.api_server([ConferenceApi])
