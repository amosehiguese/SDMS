from allauth.account.adapter import DefaultAccountAdapter


class NoMessageAccountAdapter(DefaultAccountAdapter):
    def add_message(self, request, level, message_template, message_context=None, extra_tags=''):
        # Override to completely disable messages
        pass
