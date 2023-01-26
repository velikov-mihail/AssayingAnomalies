function [out,vectx,vecty]=selectmap(lat,long,obs,x,y,method)
% PURPOSE: This function selects points on a map
%------------------------------------------------------------------------
% USAGE: [out,vectx,vecty]=selectmap(long,lat,obs,x,y,index,method)
%   where : 
%           long = n x 1 vector of coordinates on the second axis
%           lat = n x 1 vector of coordinates on the first axis
%           obs = n x 1 0-1 variable: current selection. Selected spatial units are marked with a 1
%           x = first coordinate of the selected point
%           y = second coordinate of the selected point
%           method = tells how to select points:
%                       *   method = 'point' : single point selection
%                       *   method = 'poly' : selects points inside a polygon
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1
%          vectx = vector of the first coordinates of the polygon (vectx=[] if method=1)
%          vecty = vector of the second coordinates of the polygon (vecty=[] if method=1) 
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



switch lower(method)
case 'point'
    diff=abs(long-x)*(max(lat)-min(lat))+abs(lat-y)*(max(long)-min(long));
    i=find(diff==min(diff));
    vectx=[];
    vecty=[];
    if diff(i)/((max(lat)-min(lat))*(max(long)-min(long)))<0.01
        if obs(i)==0
           obs(i)=1;        
        else
           obs(i)=0;
        end;
    end;
case 'poly' % polygon selection
    vectx=x;
    vecty=y;
    BUTTON2=0;
    p=0;
    while BUTTON2~=3
        [xp,yp,BUTTON2]=ginput(1);
        if BUTTON2~=3
            vectx=[vectx;xp];
            vecty=[vecty;yp];
            hold on;
            plot(vectx,vecty,'k');
            hold off;
        elseif BUTTON2==3 & p~=0;             
            vectx=[vectx;vectx(1)];
            vecty=[vecty;vecty(1)];
            obs2=inpolygon(long,lat,vectx,vecty);
            Iunselect=find(and(obs,obs2)~=0); % index of already selected points inside the polygon
            Iselect=find(xor(obs,obs2)~=0); % index of newly selected points
            obs(Iselect)=1;
            obs(Iunselect)=0;
        end;
        p=p+1;
    end;
end;
out=obs;