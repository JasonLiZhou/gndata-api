from django.conf.urls import url
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from tastypie.resources import Resource, ModelResource
from tastypie.utils import trailing_slash
from tastypie import fields, http
from tastypie.authentication import SessionAuthentication
from tastypie.resources import ALL

from permissions.authorization import ACLManageAuthorization
from permissions.models import SingleAccess
from account.api import UserResource


class ACLResource(ModelResource):
    user = fields.ForeignKey(UserResource, attribute='access_for')

    class Meta:
        queryset = SingleAccess.objects.all()
        resource_name = 'acl'
        authentication = SessionAuthentication()
        authorization = ACLManageAuthorization()
        include_resource_uri = False
        filtering = {
            'object_id': ALL,
            'object_type': ALL
        }
        fields = ['access_level']

    def obj_get_list(self, bundle, **kwargs):
        keys = kwargs.keys()
        if not 'object_id' in keys or not 'object_type' in keys:
            raise ValueError('Must have type and ID to manage permissions')

        qs = self._meta.queryset._clone().filter(**kwargs)
        return self.authorized_read_list(qs, bundle)


class PermissionsResourceMixin(Resource):
    """ prototype """

    def prepend_urls(self):
        return [
            url(
                r"^(?P<resource_name>%s)/(?P<pk>\w[\w/-]*)/acl%s$" % \
                (self._meta.resource_name, trailing_slash()),
                self.wrap_view('process_permissions'),
                name="api_process_permissions"
            )
        ]

    def process_permissions(self, request, **kwargs):
        try:
            bundle = self.build_bundle(data={'pk': kwargs['pk']}, request=request)
            obj = self.cached_obj_get(bundle=bundle, **self.remove_api_resource_names(kwargs))

        except ObjectDoesNotExist:
            return http.HttpGone()

        except MultipleObjectsReturned:
            return http.HttpMultipleChoices("More than one resource is found at this URI.")

        if not obj.owner.pk == request.user.pk:
            return http.HttpUnauthorized("No access to the ACL of this object")

        if not request.method in ['GET', 'PUT']:
            return http.HttpMethodNotAllowed("Use GET or PUT to manage permissions")

        acl_resource = ACLResource()

        if request.method == 'PUT':
            new_accesses = acl_resource.deserialize(request, request.body)

            update = {}
            user_resource = UserResource()
            for access in new_accesses:
                clean_user = user_resource.get_via_uri(access['user'])
                update[clean_user.pk] = access['access_level']

            obj.share(update)

        # possible option without resource
        #qs = SingleAccess.objects.filter(**params)
        #format = determine_format(request, ser, "application/json")
        #ser.serialize(qs, format)

        params = {
            'object_id': obj.pk,
            'object_type': obj.acl_type
        }
        request_bundle = acl_resource.build_bundle(request=request)

        bundles = []
        for access in acl_resource.obj_get_list(request_bundle, **params):
            bundle = acl_resource.build_bundle(obj=access, request=request)
            bundles.append(acl_resource.full_dehydrate(bundle, for_list=True))

        return acl_resource.create_response(request, bundles)