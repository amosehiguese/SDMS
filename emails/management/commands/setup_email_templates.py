from django.core.management.base import BaseCommand
from emails.models import EmailTemplate
from emails.services import EmailService

class Command(BaseCommand):
    help = 'Setup default email templates in the database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing templates',
        )
    
    def handle(self, *args, **options):
        overwrite = options['overwrite']
        created_count = 0
        updated_count = 0
        
        for email_type, config in EmailService.DEFAULT_TEMPLATES.items():
            template, created = EmailTemplate.objects.get_or_create(
                email_type=email_type,
                defaults={
                    'recipient_type': config['recipient_type'],
                    'subject': config['subject'],
                    'template_path': config['template'],
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created template: {email_type}')
                )
            elif overwrite:
                template.subject = config['subject']
                template.template_path = config['template']
                template.recipient_type = config['recipient_type']
                template.save()
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated template: {email_type}')
                )
            else:
                self.stdout.write(f'Template already exists: {email_type}')
        
        self.stdout.write('\n')
        self.stdout.write(
            self.style.SUCCESS(
                f'Setup complete! Created: {created_count}, Updated: {updated_count}'
            )
        )
        
        if not overwrite and EmailTemplate.objects.filter(email_type__in=EmailService.DEFAULT_TEMPLATES.keys()).count() > created_count:
            self.stdout.write(
                self.style.WARNING(
                    'Some templates already existed. Use --overwrite to update them.'
                )
            )