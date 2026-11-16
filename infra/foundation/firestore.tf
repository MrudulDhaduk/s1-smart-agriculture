# Managed NoSQL (storage product 2 of 3).
#   ring/membership  : hash-ring node list shared by all Partition Manager pods (Person 3)
#   alerts/*         : alert documents written by the Alert function (Person 2)
#   farm summaries   : Farm Analytics results (Person 2)
# The name "(default)" matters: the services use firestore.Client() without a database name.
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region # permanent: Firestore can never move after creation
  type        = "FIRESTORE_NATIVE"

  delete_protection_state = "DELETE_PROTECTION_DISABLED"
  # The provider default (ABANDON) would leave the database behind on destroy and break a
  # clean rebuild; we want destroy-and-rebuild to work end to end.
  deletion_policy = "DELETE"
}
