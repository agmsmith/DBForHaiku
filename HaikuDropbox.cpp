#include <stdio.h>
#include <stdlib.h>

#include "App.h"
#include <Directory.h>
#include <NodeMonitor.h>

App::App(void)
  : BApplication("application/x-vnd.lh-MyDropboxClient")
{
  //start watching ~/Dropbox folder
  BDirectory dir("/boot/home/Dropbox");
  node_ref nref;
  status_t err;
  if(dir.InitCheck() == B_OK){
    dir.GetNodeRef(&nref);
    err = watch_node(&nref, B_WATCH_DIRECTORY, BMessenger(this));
    if(err != B_OK)
      printf("Watch Node: Not OK\n");
  }
}

int
run_script(char *cmd)
{
  char buf[BUFSIZ];
  FILE *ptr;

  if ((ptr = popen(cmd, "r")) != NULL)
    while (fgets(buf, BUFSIZ, ptr) != NULL)
      (void) printf("RAWR%s", buf);
  (void) pclose(ptr);
  return 0;
}

void
App::MessageReceived(BMessage *msg)
{
  switch(msg->what)
  {
    case B_NODE_MONITOR:
    {
      printf("Received Node Monitor Alert\n");
      status_t err;
      int32 opcode;
      err = msg->FindInt32("opcode",&opcode);
      if(err == B_OK)
      {
        printf("what:%d\topcode:%d\n",msg->what, opcode);
        switch(opcode)
        {
          case B_ENTRY_CREATED:
          {
            printf("NEW FILE\n");
            run_script("python db_ls.py");
            break;
          }
          case B_ENTRY_MOVED:
          {
            printf("MOVED FILE\n");
            break;
          }
          case B_ENTRY_REMOVED:
          {
            printf("DELETED FILE\n");
            break;
          }
          default:
          {
            printf("default case opcode...\n");
          }
        }
      }
      break;
    }
    default:
    {
      printf("default msg\n");
      BApplication::MessageReceived(msg);
      break;
    }
  }
}

int
main(void)
{
  //Haiku make window code
  App *app = new App();

  app->Run();
  delete app;
  return 0;
}
