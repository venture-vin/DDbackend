from lib.drone_common.logger import log
from lib.drone_common.motor_models import motor_engine_connect, motor_client_connect
from lib.drone_common.config import config
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line

import config
from server.handlers.export_handler import ExportHandler
from server.handlers.map_handler import MapHandler, S3UploadHandler, StartStitchHandler, S3PreprocessedHandler
from server.handlers.metrics_handler import MetricsHandler
from server.handlers.organization_handlers import OrganizationHandler, OrganizationAddMemberHandler, OrganizationRemoveMemberHandler
from server.handlers.invite_handlers import InviteHandler
from server.handlers.user_handlers import UserHandler, GenerateAPIKeyHandler
from server.handlers.subscription_handlers import SubscriptionHandler
from server.handlers.annotation_handlers import AnnotationsHandler, AnnotationsV2Handler, AnnotationsV2IDHandler, AnnotationsV2CommentHandler
from server.handlers.public_share_handler import PublicShareHandler
from server.handlers.private_share_handlers import SharePlanHandler
from server.handlers.upload_handler import UploadHandler
from server.handlers.plugin_payment_handlers import PluginPaymentHandler, PluginPaymentCollectionHandler
from server.handlers.tile_handlers import TileHandler
from server.handlers.plugin_handlers import PluginCollectionHandler, PluginHandler
from server.lib.public_api_utils import Publicify

import api_handlers
import default_handlers
import device_handlers
import payment_handlers
import planning_handlers
import log_handlers
from version.version_handler import VersionHandler
import os
import socket
import secure_handlers
import template_handlers
import test_handlers
import tornado.web
import pipeline_handlers
from handlers import plan_handlers

define('develop', default=False, help='passes port number to websocket', type=bool)
define('port', default='5000', help='webserver port', type=int)
define('verbose', default=False, help='enable verbose output', type=bool)
define('identity', default=str(socket.gethostname()), help='webserver identity')

# these are no longer used, need to remove these after we update deploy scripts to not reference them
define('conduit_host', default='127.0.0.1', help='conduit zmq publish host')
define('conduit_port', default=5503, help='conduit zmq publish port')
define('pipe_host', default='127.0.0.1', help='pipeline watcher host')
define('pipe_port', default=5502, help='pipeline watcher (via conduit) port')


def log_function(handler):
    if handler.get_status() < 500:
        log_method = logger.info
    else:
        log_method = logger.warning

    request_time = 1000.0 * handler.request.request_time()
    log_method("%d %s (%s) %.2fms", handler.get_status(),
               handler._request_summary(), handler.get_current_user(), request_time)


class DroneDeployApplication(tornado.web.Application):
    MONGO_ID_REGEXP = '[a-zA-Z0-9]{24}'  # mongo ids must be 24 alphanumeric characters

    def __init__(self, **kwargs):
        dd_handlers = Publicify.convert([
            (r"/", tornado.web.RedirectHandler, {"url": "/app/dashboard"}),
            # To keep any incomeing SEO map old landing pages Jan 8 2016
            (r'/launch', tornado.web.RedirectHandler, {"url": "/", "permanent": True}),
            (r'/ag', tornado.web.RedirectHandler, {"url": "/", "permanent": True}),
            (r'/construction', tornado.web.RedirectHandler, {"url": "/", "permanent": True}),
            (r'/mining', tornado.web.RedirectHandler, {"url": "/", "permanent": True}),
            (r'/faq', tornado.web.RedirectHandler, {"url": "/", "permanent": True}),


            (r'/add_mailinglist', default_handlers.MailingListHandler),
            (r'/contact', default_handlers.ContactHandler),
            # login related routes
            # (r'/activate', secure_handlers.ActivateHandler),
            (r'/signin', secure_handlers.SignInHandler),
            (r'/signout', secure_handlers.SignOutHandler),
            (r'/pwreset', secure_handlers.PasswordResetHandler),
            (r'/pwreset_token/(\w+)', secure_handlers.PasswordResetTokenHandler),
            # TODO: temporary redirect to index until we allow signups
            (r'/welcome_token/(\w+)', secure_handlers.WelcomeTokenHandler),
            # TODO: investigate the welcome_token to ensure it is fully archaic and then remove
            (r'/signup', secure_handlers.SignupHandler),

            # chargify payments
            (r'/payment/account/new', default_handlers.CustomerNew),
            (r'/payment/webhook', default_handlers.ChargifyWebHook),
            (r'/payment/account/downgradestatus', default_handlers.DowngradeStatus),  # deprecated
            (r'/api/v1/subscription/?', SubscriptionHandler),

            # stripe
            (r'/buy/survey', payment_handlers.SurveyExplorersHandler),
            (r'/buy/survey/trial', payment_handlers.SurveyTrialExplorersHandler),
            (r'/buy/dd', payment_handlers.DDExplorersHandler),
            (r'/buy/farm', payment_handlers.FarmExplorersHandler),
            (r'/buy/farm/trial', payment_handlers.FarmTrialExplorersHandler),
            (r'/buy/partner', payment_handlers.PartnerExplorersHandler),
            (r'/buy/edu', payment_handlers.EduExplorersHandler),
            (r'/stripe/(\w+)', payment_handlers.StripeHandler),
            (r'/success', payment_handlers.StripeSuccessHandler),
            (r'/failure', payment_handlers.StripeFailureHandler),


            # shareing routes
            (r'/share/private/plan/(.+)', SharePlanHandler),

            # authenticated api routes
            (r'/api/v1/add_device/(\w+)', secure_handlers.AddDeviceHandler),
            (r'/api/v1/role/(\w+)', api_handlers.RoleHandler),
            (r'/api/v1/roles?/?', api_handlers.RolesHandler),
            (r'/api/v1/rating/(\w+)', api_handlers.RatingHandler),
            (r'/api/v1/copilot', api_handlers.CopilotHandler),
            (r'/api/v1/quality', api_handlers.QualityHandler),
            (r'/api/v1/devices', device_handlers.DevicesHandler),
            (r'/api/v1/devices/(\w+)', device_handlers.DeviceHandler),
            (r'/api/v1/parameters/?', api_handlers.ParameterHandler),
            (r'/api/v1/parameters/(\w+)/(\w+)', api_handlers.ParameterHandler),
            (r'/api/v1/parameters/(\w+)', api_handlers.ParameterHandler),
            (r'/api/v1/annotations/(\w+)', AnnotationsHandler),
            (r'/api/v2/annotations/?', AnnotationsV2Handler),
            (r'/api/v2/annotations/(\w+)', AnnotationsV2IDHandler),
            (r'/api/v2/annotations/(\w+)/comments/?', AnnotationsV2CommentHandler),

            (r'/api/v1/user', UserHandler),

            # initialize an organization's invited member
            (r'/api/v1/invite/(\w+)', InviteHandler),

            # version check
            (r'/api/v1/version/([\w\.]+)/(\w+)', VersionHandler),

            # Plan handlers and methods
            (r'/api/v1/plan/?', plan_handlers.PlanHandler),
            (r'/api/v1/plan/(\w+)?', plan_handlers.PlanHandler),
            Publicify(r'/api/v2/plan?/?', plan_handlers.PlanHandlerV2),
            Publicify(r'/api/v2/plan?/(?P<id>[\w\d]+)', plan_handlers.PlanHandlerV2),

            (r'/api/v1/plan/(\w+)/startstitch/?', StartStitchHandler),
            (r'/api/v1/plan/(\w+)/view/?', api_handlers.ViewSettingsHandler),
            (r'/api/v1/plan/(\w+)/view/([^/]+)', api_handlers.ViewSettingsHandler),

            (r'/api/v1/layer', api_handlers.LayerHandler),
            (r'/api/v1/layer/(\w+)', api_handlers.LayerHandler),

            (r'/api/v1/mobilelog', api_handlers.MobileLogHandler),

            (r'/api/v1/message', api_handlers.MessageHandler),
            (r'/api/v1/message/(\w+)', api_handlers.MessageHandler),
            (r'/api/v1/log', log_handlers.LogHandler),
            (r'/api/v1/log/(\w+)', log_handlers.LogHandler),
            (r'/api/v1/status/(\w+)', api_handlers.StatusHandler),
            (r'/api/v1/location/(\w+)', api_handlers.LocationHandler),
            (r'/api/v1/log/(\w+)/(\w+)', log_handlers.LogHandler),
            (r'/api/v1/uploads/([\w\-\.]+)/(\w+)/(.*)', UploadHandler),

            (r'/api/v1/network', api_handlers.NetworkHandler),
            (r'/api/v1/network/(\w+)', api_handlers.NetworkHandler),
            (r'/api/v1/apikey', GenerateAPIKeyHandler),
            (r'/api/v1/weather', api_handlers.WeatherHandler),
            (r'/api/v1/geocode', api_handlers.GeocodeHandler),
            (r'/api/v1/images/(\w+)', api_handlers.ImageHandler),
            (r'/api/v1/tiles/(\w+)/(\w+)/(\w+)', TileHandler),

            (r'/api/v1/imagelist/(\w+)', api_handlers.ImageListHandler),
            (r'/api/v1/airspace', api_handlers.AirspaceHandler),
            (r'/api/v1/export/(\w+)?', ExportHandler),
            Publicify(r'/api/v2/export/?', ExportHandler),
            Publicify(r'/api/v2/export/(?P<id>\w+)', ExportHandler),
            (r'/api/v1/shortener', api_handlers.UrlShortenerHandler),
            (r'/api/v1/camera', api_handlers.CameraHandler),
            (r'/api/v1/camera/(\w+)', api_handlers.CameraHandler),
            (r'/api/v1/pipeline/plan/(\w+)', pipeline_handlers.RawPlanHandler),
            (r'/api/v1/pipeline/view/(\w+)', pipeline_handlers.RawViewSettingsHandler),
            (r'/api/v1/pipeline/email/(\w+)', pipeline_handlers.PipelineEmailHandler),
            (r'/api/v1/pipeline/export_email/(\w+)', pipeline_handlers.ExportEmailHandler),
            (r'/api/v1/pipeline/s3upload', S3UploadHandler),
            (r'/api/v1/pipeline/s3preprocessed', S3PreprocessedHandler),

            # we should replace api/v1/pipeline with api/v1/map, leaving in for now for backwards compatability
            (r'/api/v1/pipeline/(\w+)?', MapHandler),
            (r'/api/v1/map/({})?'.format(self.MONGO_ID_REGEXP), MapHandler),
            (r'/api/v1/pipeline/(\w+)/(\w+)', pipeline_handlers.PipelineCopyHandler),
            (r'/api/v1/sync', plan_handlers.SyncHandler),

            # Analytics
            (r'/api/v1/track', api_handlers.TrackHandler),
            (r'/api/v1/metrics', MetricsHandler),

            # Organization
            (r'/api/v1/organization/?', OrganizationHandler),
            (r'/api/v1/organization/({})'.format(self.MONGO_ID_REGEXP), OrganizationHandler),
            (r'/api/v1/organization/({})/addmember'.format(self.MONGO_ID_REGEXP), OrganizationAddMemberHandler),
            (r'/api/v1/organization/({})/removemember/?'.format(self.MONGO_ID_REGEXP), OrganizationRemoveMemberHandler),

            # Plugins
            (r'/api/v1/plugins?/?', PluginCollectionHandler),
            (r'/api/v1/plugins?/({})'.format(self.MONGO_ID_REGEXP), PluginHandler),
            (r'/api/v1/plugin_payments?/?', PluginPaymentCollectionHandler),
            Publicify(r'/api/v1/plugin_payments/(?P<id>{})'.format(self.MONGO_ID_REGEXP), PluginPaymentHandler),

            (r'/api/v1/application/?', api_handlers.ApplicationHandler),
            (r'/api/v1/application/(\w+)', api_handlers.ApplicationHandler),

            (r'/images/thumb/(\w+)/(\w+)/([\w\.]+)', api_handlers.OldImageThumbHandler),
            (r'/images/thumb/(\w+)/([\w\.]+)/(\w+)/(.*)', api_handlers.ImageThumbHandler),

            # flight planning api routes
            (r'/api/v1/planning/vertical/(?P<latlng>[^\/]+)/(?P<altitude>[^\/]+)/(?P<profile_name>[^\/]+)', planning_handlers.VerticalHandler),
            (r'/api/v1/planning/surveillance/(?P<home_latlng>[^\/]+)/(?P<target_latlng>[^\/]+)/(?P<altitude>[^\/]+)/(?P<profile_name>[^\/]+)', planning_handlers.SurveillanceHandler),
            (r'/api/v1/planning/delivery/(?P<home_latlng>[^\/]+)/(?P<target_latlng>[^\/]+)/(?P<altitude>[^\/]+)/(?P<profile_name>[^\/]+)', planning_handlers.DeliveryHandler),
            (r'/api/v1/planning/structure/(?P<latlng>[^\/]+)/(?P<radius>[^\/]+)/(?P<height>[^\/]+)/(?P<iterations>[^\/]+)/(?P<profile_name>[^\/]+)', planning_handlers.StructureHandler),
            (r'/api/v1/planning/custom/(?P<latlngs>[^\/]+)/(?P<altitude>[^\/]+)/(?P<profile_name>[^\/]+)', planning_handlers.CustomHandler),
            (r'/api/v1/planning/survey/(?P<latlngs>[^\/]+)/(?P<gsd>[^\/]+)/(?P<camera_id>[^\/]+)/(?P<side_overlap>[^\/]+)/(?P<front_overlap>[^\/]+)/(?P<profile_name>[^\/]+)', planning_handlers.SurveyHandler),
            (r'/api/v1/planning/djisurvey/(?P<latlngs>[^\/]+)/(?P<camera_id>[^\/]+)', planning_handlers.DJISurveyHandler),
            (r'/api/v1/planning/djisurvey/(?P<latlngs>[^\/]+)', planning_handlers.DJISurveyHandler),  # to support older versions of the app which didn't send a cam id - 6/4/15

            # authenticated external routes
            (r'/jspm_packages/.*', default_handlers.JspmStaticResourcesHandler),
            (r'/app2/.*', default_handlers.AuthenticatedDefaultHandlerV2),
            (r'/app/cache.manifest2', default_handlers.AuthenticatedCacheManifestHandlerV2),
            (r'/app/viewer', PublicShareHandler),
            (r'/app/cache.manifest', default_handlers.AuthenticatedCacheManifestHandler),
            (r'/app/.*', default_handlers.AuthenticatedDefaultHandler),
            (r'/mobile/.*', default_handlers.AuthenticatedMobileHandler),

            (r'/connection-test', default_handlers.ConnectionTestHandler),

            # administrative routes
            (r'/api/v1/user/impersonate/(.*)', secure_handlers.ImpersonateHandler),
            (r'/api/v1/user/pw', secure_handlers.PasswordChangeHandler),

            # create example data for tour
            (r'/api/v1/user/template', template_handlers.TemplateHandler),

            # test routes
            (r'/api/v1/test/user/reset', test_handlers.TestUserResetHandler),

            # public API spec
            (r'/public/api/(public_apis\.yaml)', tornado.web.StaticFileHandler,
             {'path': os.path.join(os.path.dirname(__file__), 'api_specs')}),
        ])

        dd_settings = {
            'debug': config.ENVIRONMENT != "prod",
            'template_path': os.path.join(os.path.dirname(__file__), "../templates"),
            'static_path': os.path.join(os.path.dirname(__file__), "../static"),
            'cookie_secret': config.JWT_SECRET,
            "xsrf_cookies": False,
            "gzip": True,
            'login_url': '/signin',
            'log_function': log_function
        }
        dd_settings.update(kwargs)

        motor_engine_connect(IOLoop.instance())

        self.db = motor_client_connect()

        self.dd_env = os.environ.get('DDENV', 'dev')

        self.sentry_client = log.async_sentry_client

        tornado.web.Application.__init__(self, dd_handlers, **dd_settings)


if __name__ == '__main__':

    options.logging = 'none'
    parse_command_line()

    global logger
    logger = log.get()

    dd_app = DroneDeployApplication()
    dd_app.listen(options.port, xheaders=True)
    logger.info('webserver listening on port {}'.format(options.port))
    IOLoop.instance().set_blocking_log_threshold(10)
    IOLoop.instance().start()
