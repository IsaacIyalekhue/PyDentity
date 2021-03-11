from aiohttp import (
    web,
    ClientSession,
    ClientRequest,
)
from pubsub import pub

from .controllers.connections import ConnectionsController
from .controllers.messaging import MessagingController
from .controllers.mediation import MediationController
from .controllers.schema import SchemaController
from .controllers.wallet import WalletController
from .controllers.definitions import DefinitionsController
from .controllers.issuer import IssuerController
from .controllers.proof import ProofController
from .controllers.ledger import LedgerController
from .controllers.credential import CredentialController
from .controllers.multitenant import MultitenancyController
from .controllers.server import ServerController
from .controllers.oob import OOBController
from .controllers.action_menu import ActionMenuController
from .controllers.revocation import RevocationController

import logging

logger = logging.getLogger("aries_controller")

class AriesAgentController:

    ## TODO rethink how to initialise. Too many args?
    ## is it important to let users config connections/issuer etc
    def __init__(
        self,
        webhook_host: str,
        webhook_port: int,
        admin_url: str,
        webhook_base: str = "",
        connections: bool = True,
        messaging: bool = True,
        multitenant: bool = False,
        mediation: bool = True,
        issuer: bool = True,
        action_menu: bool = True,
        revocations: bool = True,
        api_key: str = None,
        jwt_token: str = None,
    ):

        self.webhook_site = None
        self.admin_url = admin_url
        if webhook_base:
            self.webhook_base = webhook_base
        else:
            self.webhook_base = ""
        self.webhook_host = webhook_host
        self.webhook_port = webhook_port
        self.connections_controller = None

        if api_key:
            headers = {"X-API-Key": api_key}
            self.client_session: ClientSession = ClientSession(headers=headers)
        else:
            self.client_session: ClientSession = ClientSession()

        if jwt_token:
            headers = {'Authorization': 'Bearer ' + jwt_token, 'content-type': "application/json"}
            self.client_session: ClientSession = ClientSession(headers=headers)
        else:
            self.client_session: ClientSession = ClientSession()

        if connections:
            self.connections = ConnectionsController(self.admin_url, self.client_session)
        if messaging:
            self.messaging = MessagingController(self.admin_url, self.client_session)

        self.proofs = ProofController(self.admin_url, self.client_session)
        self.ledger = LedgerController(self.admin_url, self.client_session)
        self.credentials = CredentialController(self.admin_url, self.client_session)
        self.server = ServerController(self.admin_url, self.client_session)
        self.oob = OOBController(self.admin_url, self.client_session)

        if multitenant:
            self.multitenant = MultitenancyController(self.admin_url, self.client_session)

        if mediation:
            self.mediation = MediationController(self.admin_url, self.client_session)

        if issuer:
            self.schema = SchemaController(self.admin_url, self.client_session)
            self.wallet = WalletController(self.admin_url, self.client_session)
            self.definitions = DefinitionsController(self.admin_url, self.client_session)
            self.issuer = IssuerController(self.admin_url, self.client_session, self.connections,
                                           self.wallet, self.definitions)

        if action_menu:
            self.action_menu = ActionMenuController(self.admin_url, self.client_session)

        if revocations:
            self.revocations = RevocationController(
                self.admin_url,
                self.client_session
            )

        
    # def update_jwt_token(self, api_key: str):
    #     headers = {"X-API-Key": api_key}
    #     self.client_session: ClientSession = ClientSession(headers=headers)
        # if connections:
        #     self.connections = ConnectionsController(self.admin_url, self.client_session)
        # if messaging:
        #     self.messaging = MessagingController(self.admin_url, self.client_session)


    def register_listeners(self, listeners, defaults=True):
        if defaults:
            if self.connections:
                pub.subscribe(self.connections.default_handler, "connections")
            if self.messaging:
                pub.subscribe(self.messaging.default_handler, "basicmessages")
            if self.proofs:
                pub.subscribe(self.proofs.default_handler, "present_proof")

        for listener in listeners:
            self.add_listener(listener)

    def add_listener(self, listener):
        pub.subscribe(listener["handler"], listener["topic"])

    def remove_listener(self, listener):
        if pub.isSubscribed(listener["handler"], listener["topic"]):
            pub.unsubscribe(listener["handler"], listener["topic"])
        else:
            logger.debug("Listener not subscribed", listener)

    def remove_all_listeners(self, topic: str = None):
        # Note advanced use of function can include both listenerFilter and topicFilter for this
        # Add when needed
        pub.unsubAll(topicName=topic)

    async def listen_webhooks(self):
        app = web.Application()
        app.add_routes([web.post(self.webhook_base + "/topic/{topic}/", self._receive_webhook)])
        runner = web.AppRunner(app)
        await runner.setup()
        # self.webhook_site = web.TCPSite(runner, host=self.webhook_host, port=self.webhook_port, sock=socket, reuse_address=True, reuse_port=True)
        self.webhook_site = web.TCPSite(runner, host=self.webhook_host, port=self.webhook_port)
        await self.webhook_site.start()

    async def _receive_webhook(self, request: ClientRequest):
        topic = request.match_info["topic"]
        payload = await request.json()
        await self._handle_webhook(topic, payload)
        return web.Response(status=200)

    async def _handle_webhook(self, topic, payload):
        logging.debug(f"Handle Webhook - {topic}", payload)
        pub.sendMessage(topic, payload=payload)
        # return web.Response(status=200)

    async def terminate(self):
        await self.client_session.close()
        if self.webhook_site:
            await self.webhook_site.stop()
