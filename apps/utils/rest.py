# coding: utf-8
from .api import ApiHandler
from apps.accounts.models import User # FIXME need refactoring

from mongoengine.errors import DoesNotExist, MultipleObjectsReturned, NotUniqueError, ValidationError


class MongoEngineDataManager(object):
    # user_mapping_path must be in the format: a.b.c where all fiels are required to avoid AttributeError for None
    def __init__(self, model, user=None, ip=None, user_mapping_path=None):
        self.model = model
        self.user = user
        self.ip = ip
        self.user_mapping_path = user_mapping_path

    def filter_by_user(self, objs):
        if hasattr(self.model, 'user'):
            objs = objs(user=self.user)
        elif self.user_mapping_path:
            # Only for small collections
            ids = []
            for obj in objs:
                try:
                    user = eval('obj.' + self.user_mapping_path)
                except AttributeError: # some field is not required
                    user = None
                if user == self.user:
                    ids.append(obj.id)
            objs = objs.filter(id__in=ids)
        return objs

    def read_list(self, initial=0, amount=50):
        objs = self.model.objects.all()[initial:initial+amount]
        if self.user and self.user_mapping_path:
            objs = self.filter_by_user(objs)
        return objs

    def count(self):
        return self.read_list().count()

    def read(self, identifier):
        try:
            return self.read_list().get(pk=identifier)
        except self.model.DoesNotExist:
            return None

    def create(self, data, persist=True):
        obj = self.model(**data)
        if hasattr(self.model, 'user'):
            obj.user = self.user
        elif self.user and self.user_mapping_path:
            try:
                user = eval('obj.' + self.user_mapping_path)
            except AttributeError:
                print('obj.' + self.user_mapping_path)
                user = None
            if user != self.user:
                raise AssertionError('Not enough permissions to create this object')
        if persist:
            obj.save()
        return obj

    def update(self, identifier, data):
        obj = self.read(identifier)
        if obj:
            update_query = {}
            for key, value in data.items():
                if hasattr(obj, key):
                    update_query['set__%s' % key] = value
            obj.update(**update_query)
            obj.reload()
        return obj

    def delete(self, identifier):
        obj = self.read(identifier)
        if obj:
            obj.delete()
        return obj


class RestHandler(ApiHandler):
    model = None
    user_mapping_path = None
    data_manager = MongoEngineDataManager
    perm_public = 'CRLUD'
    perm_user = 'CRLUD'
    perm_admin = 'CRLUD'

    def prepare(self):
        super(RestHandler, self).prepare()
        self.data_manager = self.data_manager(self.model, user=self.get_current_user(),
            ip=self.request.remote_ip, user_mapping_path=self.user_mapping_path)

    def check_permission(self, action):
        user = self.get_current_user()
        admin = self.is_admin_user()
        if action in self.perm_public or (user and action in self.perm_user) or (admin and action in self.perm_admin):
            pass # ok
        else:
            self.raise403()

    # CREATE /objs
    def post(self):
        self.check_permission('C')
        data = self.get_request_data()
        try:
            obj = self.data_manager.create(data)
        except (NotUniqueError, ValidationError) as e:
            self.raise400(msg=str(e))
        else:
            if obj:
                self.answer(obj)
            else:
                self.raise404()

    # LIST /objs/
    # READ /objs/:id
    def get(self, identifier=None):
        if identifier:
            self.check_permission('R')
            if identifier == 'count':
                self.answer(self.data_manager.count())
            else:
                try:
                    obj = self.data_manager.read(identifier)
                except (MultipleObjectsReturned) as e:
                    logging.error(str(e))
                    logging.error(data)
                    logging.exception(e)
                    self.raise500()
                else:
                    if obj:
                        self.answer(obj)
                    else:
                        self.raise404()
        else:
            self.check_permission('L')
            # FIXME pagination
            initial = int(self.get_argument('initial', default=0))
            amount = int(self.get_argument('amount', default=50))
            amount = max(amount, initial) # amount < initial validation
            amount = min(amount, initial+500) # more than 500 records protection
            objs = self.data_manager.read_list(initial=initial, amount=amount)
            self.answer(objs)

    # UPDATE /objs/:id
    def put(self, identifier):
        self.check_permission('U')
        data = self.get_request_data()
        try:
            obj = self.data_manager.update(identifier, data)
        except (NotUniqueError, ValidationError) as e:
            self.raise400(str(e))
        except (MultipleObjectsReturned) as e:
            logging.error(str(e))
            logging.error(data)
            logging.exception(e)
            self.raise500()
        else:
            if obj:
                self.answer(obj)
            else:
                self.raise404()

    # DELETE /objs/:id
    def delete(self, identifier):
        self.check_permission('D')
        try:
            obj = self.data_manager.delete(identifier)
            if obj:
                self.answer(obj)
            else:
                self.raise404()
        except (MultipleObjectsReturned) as e:
            logging.error(str(e))
            logging.error(data)
            logging.exception(e)
            self.raise500()
