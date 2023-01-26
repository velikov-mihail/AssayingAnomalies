function [bclas1, bclas2] = numbcla(nobs,nbcla)
% PURPOSE: This function creates boundaries of classes for allocating
%nobs observations to nbcla classes
%--------------------------------------------------------------
% USAGE: [bclas1, bclas2] = numbcla(nobs,nbcla)
%   where:   nobs =  nx1 vector where classes are created
%            nbcla = number of classes to create
%--------------------------------------------------------------
% OUTPUTS: bclass1 = indices of the lower boundaries of the classes
%          bclass2 = indices of the upper boundaries of the classes
%--------------------------------------------------------------
% Yves Aragon, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


ngcl = rem(nobs,nbcla);
npcl = nbcla - ngcl;
tpcl = floor(nobs/nbcla);
if ngcl == 0
t1 = ' Creation of the sizes of the classes : No remainder';
t1;
  i = (1:nbcla)';
 un = ones(nbcla,1);
 bclas1 = (i - un) * tpcl + un;
 bclas2 = i * tpcl;
else
tgcl = tpcl+1;
 t2 = ' There is a remainder, large size classes';
 t2;
 tgcl;
i = (1:npcl)';
 un1 = ones(npcl,1);
 bclas1p = (i - un1) * tpcl + un1;
 bclas2p = i * tpcl;

i = (1:ngcl)';
cale = npcl*tpcl; un1 = (cale+1) * ones(ngcl,1);
un0 = ones(ngcl,1);
 bclas1g = (i - un0) * tgcl + un1; 
 bclas2g = bclas1g + (tgcl-1) * un0;
 
bclas1 = [bclas1p; bclas1g];
bclas2 = [bclas2p; bclas2g];


end

