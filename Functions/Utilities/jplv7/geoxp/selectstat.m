function [out,varargout]=selectstat(method,obs,variable,varargin)
% PURPOSE: This function selects objects on a statistic graph
%------------------------------------------------------------------------
% USAGE: [out,...]=selectstat(method,obs,variable,...)
%   where : method = type of statistic graph. Inputs and outputs depend on this parameter (see below)
%           obs = n x 1 0-1 variable: current selection. Selected spatial units are marked with a 1
%           variable = (n x 1) variable used to plot the statistic graph
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1
%------------------------------------------------------------------------
% MANUAL: The usage depends on the value of the 'method' parameter:
%   * method='box' : [out]=selectstat('box',obs,variable,frtbasse,frthaute,q1,med,q3,y) : Selection on a box and whiskers plot
%       where : frtbasse = the low value
%               frthaute = the high value
%               q1 = the lower quartile
%               med = the median
%               q3 = the upper quartile
%               y = second coordinate of the selected point
%-----------------
%   * method='density' : [out,inter,intersav,p]=selectstat('density',obs,variable,inter,intersav,p,x) : Selection on a density plot
%       where : inter = used to stock selected points
%               intersav = used to stock the selected interval
%               p = flag
%               x = first coordinate of the selected point
%       output : inter = modified variable inter
%                intersav = modified variable intersav
%                p = modified flag
%-----------------
%   * method='histo' : [out]=selectstat('histo',obs,variable,edge2,N,x,y) : Selection on an histogram
%       where : edge2 = vector of the edges of the classes of the histogram (edge2(end)=inf)
%               N = vector of the number of elements in the classes of the histogram
%               x = first coordinate of the selected  point
%               y = second coordinate of the selected  point
%-----------------
%   * method='bar' : [out]=selectstat('bar',obs,variable,edge2,N,x,y,edgeaff) : Selection on a bar plot
%       where : edge2 = vector of the edges of the classes of the bar plot (edge2(end)=inf)
%               N = vector of the number of elements in the classes of the bar plot
%               x = first coordinate of the selected  point
%               y = second coordinate of the selected  point
%               edgeaff = vector of the edges of the bars to plot
%-----------------
%   * method='moran' : [out,...]=selectstat('moran',obs,variable,submethod,...) : Seection on a moran plot
%       ** submethod='quadrant' : [out,affq1,affq2,affq3,affq4]=selecstat('moran',obs,variable,'quadrant',q1,q2,q3,q4,Q1,Q2,Q3,Q4,affq1,affq2,affq3,affq4) : Quadrant selection
%           where : q1 = handle of the first quadrant button
%                   q2 = handle of the second quadrant button
%                   q3 = handle of the third quadrant button
%                   q4 = handle of the fourth quadrant button
%                   Q1 = indices of the points in the first quadrant
%                   Q2 = indices of the points in the second quadrant
%                   Q3 = indices of the points in the third quadrant
%                   Q4 = indices of the points in the fourth quadrant
%                   affq1 = flag that tells if the first quadrant must be displayed
%                   affq2 = flag that tells if the second quadrant must be displayed
%                   affq3 = flag that tells if the third quadrant must be displayed
%                   affq4 = flag that tells if the fourth quadrant must be displayed
%           output : affq1 = modified flag
%                    affq2 = modified flag
%                    affq3 = modified flag
%                    affq4 = modified flag
%
%       ** submethod='point' : [out]=selectstat('moran',obs,variable,'point',WX,x,y) : Point selection
%           where : WX = (n x 1) variable to study on the second axis
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected point
%
%       ** submethod='poly' : [out,vectx,vecty]=selectstat('moran',obs,variable,'poly',WX,x,y) : Polygon selection
%           where : WX = (n x 1) variable to study on the second axis
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected  point
%           output : vectx = vector of the first coordinates of the points of the polygon
%                    vecty = vector of the second coordinates of the points of the polygon
%-----------------
%   * method='neighbour' : [out,L,L2]=selectstat('neighbour',obs,variable,submethod,I,J,W,L,L2,x,y) : Selection on the map
%       ** submethod='mappoint' : [out,L,Iclick]=selectstat('neighbour',obs,variable,'mappoint',I,J,W,L,x,y,long,lat,Iclick); % point selection
%           where : I = row indices of the elements that are different of zero in W
%                   J = column indices of the elements that are different of zero in W
%                   W = weigh matrix
%                   L = linkage matrix
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected  point
%                   long = longitudes of the points of the map
%                   lat = latitudes of the points of the map
%                   Iclick = (n x 1) 0-1 variable that tells the points that were selected
%           output : L = modified linkage matrix
%                    Iclick = modified selected points
%       ** submethod='mappoly' : [out,L,Iclick,vectx,vecty]=selectstat('neighbour',obs,variable,'mappoly',I,J,W,L,x,y,long,lat,Iclick); % polygon selection
%           where : I = row indices of the elements that are different of zero in W
%                   J = column indices of the elements that are different of zero in W
%                   W = weigh matrix
%                   L = linkage matrix
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected point
%                   long = longitudes of the points of the map
%                   lat = latitudes of the points of the map
%                   Iclick = (n x 1) 0-1 variable that tells the points that were clicked
%           output : L = modified linkage matrix
%                    Iclick = modified clicked points
%       ** submethod='neigh' [out,L,L2]=selectstat('neighbour',obs,variable,'neigh',I,J,W,L,L2,x,y);
%           where : I = row indices of the elements that are different of zero in W
%                   J = column indices of the elements that are different of zero in W
%                   W = weigh matrix
%                   L = linkage matrix
%                   L2 = display matrix
%                   x = first coordinate of the selected point
%                   y = second coordinate of the selected point
%           output : L = modified linkage matrix
%                    L2 = modified display matrix
%-----------------
%   * method='scatter' : [out,...]=selectstat('scatter',obs,variable,submethod,...) : Selection on a scatter plot
%       ** submethod='class' : [obs,affc]=selectstat('scatter',obs,var1,'class',var2,BUTTON,Hbutt,vectclass,affc) : class selection
%
%       ** submethod='point' : [out]=selecstat('scatter',obs,variable,'point',var2,x,y) : Point selection
%           where : var2 = (n x 1) variable to study on the second axis
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected  point
%
%       ** submethod='poly' : [out,vectx,vecty]=selectstat('scatter',obs,variable,'poly',var2,x,y) : Polygon selection
%           where : var2 = (n x 1) variable to study on the second axis
%                   x = first coordinate of the selected point
%                   y = second coordinate of the selected  point
%           output : vectx = vector of the first coordinates of the points of the polygon
%                    vecty = vector of the second coordinates of the points of the polygon
%-----------------
%   * method='vario' : [out,...]=selectstat('vario',obs,variable,submethod,...) : Selection on a variocloud
%       ** submethod='point' : [out,L]=selecstat('vario',obs,variable,'point',H,V,Htri,Vtri,L,x,y) : Point selection
%           where : H = distance matrix
%                   V = vario matrix
%                   Htri = distance vector
%                   Vtri = vario vector
%                   L = linkage matrix
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected point
%           output : L = modified linkage matrix
%
%       ** submethod='poly' : [out,L,vectx,vecty]=selecstat('vario',obs,variable,'poly',H,V,Htri,Vtri,L,x,y) : Polygon selection
%           where : H = distance matrix
%                   V = vario matrix
%                   Htri = distance vector
%                   Vtri = vario vector
%                   L = linkage matrix
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected  point
%           output : L = modified linkage matrix
%                    vectx = vector of the first coordinates of the points of the polygon
%                    vecty = vector of the second coordinates of the points of the polygon
%-----------------
%   * method='angle' : [out,...]=selectstat('angle',obs,variable,submethod,...) : Selection on an angle plot
%       ** submethod='point' : [out,L]=selecstat('angle',obs,variable,'point',Theta,V,Thetatri,Vtri,L,x,y) : Point selection
%           where : Theta = angle matrix
%                   V = difference matrix
%                   Thetatri = angle vector
%                   Vtri = difference vector
%                   L = linkage matrix
%                   x = first coordinate of the selected point
%                   y = second coordinate of the selected point
%           output : L = modified linkage matrix
%
%       ** submethod='poly' : [out,L,vectx,vecty]=selecstat('angle',obs,variable,'poly',Theta,V,Thetatri,Vtri,L,x,y) : Polygon selection
%           where : Theta = angle matrix
%                   V = difference matrix
%                   Thetatri = angle vector
%                   Vtri = difference vector
%                   L = linkage matrix
%                   x = first coordinate of the selected  point
%                   y = second coordinate of the selected point
%           output : L = modified linkage matrix
%                    vectx = vector of the first coordinates of the points of the polygon
%                    vecty = vector of the second coordinates of the points of the polygon
%-----------------
%   * method='polybox' : out=selectstat('polybox',obs,variable,frtbasse,frthaute,q1,med,q3,vectbox,valeurs,var2,x,y); selection on a multiple box and whiskers plot
%       where : frtbasse = vector of the low values
%               frthaute = vector of the high values
%               q1 = vector of the lower quartiles
%               med = vector of the medians
%               q3 = vector of the upper quartile
%               vectbox = cell of vectors containing the values of the first variable for every value of the second variable
%               valeurs = vector of the values of the second variable
%               var2 = vector of the second variable
%               x = first coordinate of the selected  point 
%               y = second coordinate of the selected  point
%-----------------
%   * method='gini' : [out,GG,xsol]=selectstat('gini',obs,variable,FuncF,FuncG,Xk,x); selection on a gini plot
%       where : FuncF = vector of the values of the step function built thanks to f (see ginimap.m)
%               FuncG = vector of the values of the step function built thanks to g (see ginimap.m)
%               Xk = vector of the unique values of variables
%               x = first coordinates of the selected  point
% ----------------
%   * method='scatter3d' : obs=selectstat('scatter3d',obs,var1,var2,var3,cpa) : selection on a 3D scatterplot
%--------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr

switch lower(method)
case 'box'
    frtbasse=varargin{1};
    frthaute=varargin{2};
    q1=varargin{3};
    med=varargin{4};
    q3=varargin{5};
    y=varargin{6};
    if y>=frtbasse & y <q1
        I=find(variable>=frtbasse & variable<q1);
    elseif y>=q1 & y<med
        I=find(variable>=q1 & variable<med);
    elseif y>=med & y<q3
        I=find(variable>=med & variable<q3);
    elseif y>=q3 & y<frthaute
        I=find(variable>=q3 & variable<=frthaute);
    else
        diff=abs(variable-y);
        i=find(diff==min(diff));
        if (diff(i)/max(variable))<0.01
            I=i;
        else 
            I=[];
        end;
    end;
    if ~isempty(I)
        if obs(I(1))==0;
            obs(I)=1;
        else
            obs(I)=0;
        end;
    end;
    out=obs;
case 'density'
    inter=varargin{1};
    intersav=varargin{2};
    p=varargin{3};
    x=varargin{4};
    BUTTON=varargin{5};
    if isempty(inter)
        inter=x;
        p=0;
        intersav=[];
    end;
    if  BUTTON~=3 & BUTTON~=2 & p==1
        inter=[inter x];
        I=find(variable>=min(inter) & variable<=max(inter));
        if ~isempty(I)
            obs(I)=1-obs(I);
        end;
        intersav=sort(inter);
        inter=[];
     end;
     p=1;
     out=obs;
     varargout{1}=inter;
     varargout{2}=intersav;
     varargout{3}=p;
 case 'histo'
     edge2=varargin{1};
     N=varargin{2};
     x=varargin{3};
     y=varargin{4};
     Xn=sort([edge2,x]);
     i=find(Xn==x)-1;           
     if i~=0 & y<=N(i)
         J=find(variable<edge2(i+1) & variable>=edge2(i));
         if ~isempty(J) & obs(J(1))==0
            obs(J)=1;
         elseif ~isempty(J)
            obs(J)=0;
         end;
      end;
      out=obs;
 case 'bar'
     edge2=varargin{1};
     edge2=edge2-0.4;
     N=varargin{2};
     x=varargin{3};
     y=varargin{4};
     edgeaff=varargin{5};
     Xn=sort([edgeaff-0.3,x]);
     i=find(Xn==x)-1;           
     if i~=0 & y<=N(i)
         J=find(variable<edge2(i+1) & variable>=edge2(i));
         if ~isempty(J) & obs(J(1))==0
            obs(J)=1;
         elseif ~isempty(J)
            obs(J)=0;
         end;
      end;
      out=obs;
  case 'moran'
      switch lower(varargin{1})
      case 'quadrant'
          BUTTON=varargin{2};
          q1=varargin{3};
          q2=varargin{4};
          q3=varargin{5};
          q4=varargin{6};
          Q1=varargin{7};
          Q2=varargin{8};
          Q3=varargin{9};
          Q4=varargin{10};
          affq1=varargin{11};
          affq2=varargin{12};
          affq3=varargin{13};
          affq4=varargin{14};
          if BUTTON==49
            set(q1,'Value',1-get(q1,'Value'));
            affq1=get(q1,'Value');
            if ~isempty(Q1) & get(q1,'Value')==1
                obs(Q1)=1;         
            elseif ~isempty(Q1) & get(q1,'Value')==0
                obs(Q1)=0;        
            end;
        elseif BUTTON==50
            set(q2,'Value',1-get(q2,'Value'));
            affq2=get(q2,'Value');
            if ~isempty(Q2) & get(q2,'Value')==1
                obs(Q2)=1;
            elseif ~isempty(Q2) & get(q2,'Value')==0
                obs(Q2)=0;
            end;
        elseif BUTTON==51
            set(q3,'Value',1-get(q3,'Value'));
            affq3=get(q3,'Value');
            if ~isempty(Q3) & get(q3,'Value')==1
                obs(Q3)=1;
            elseif ~isempty(Q3) & get(q3,'Value')==0
                obs(Q3)=0;
            end;
        elseif BUTTON==52
            set(q4,'Value',1-get(q4,'Value'));
            affq4=get(q4,'Value');
            if ~isempty(Q4) & get(q4,'Value')==1
                obs(Q4)=1;
            elseif ~isempty(Q4) & get(q4,'Value')==0
                obs(Q4)=0;
            end;
        end;
        varargout{1}=affq1;
        varargout{2}=affq2;
        varargout{3}=affq3;
        varargout{4}=affq4;
        out=obs;
    case 'point'
        WX=varargin{2};
        x=varargin{3};
        y=varargin{4};
        L=varargin{5};
        W=varargin{6};
        outsav=obs;
        [out ,vectx,vecty]=selectmap(WX,variable,obs,x,y,'point');
        Iclick=find((outsav-out)~=0);
        Jvois=find(W(Iclick,:)~=0);
        L(Iclick,Jvois)=1-L(Iclick,Jvois);
        L(Jvois,Iclick)=1-L(Jvois,Iclick);
        varargout{1}=L;
    case 'poly'
        WX=varargin{2};
        x=varargin{3};
        y=varargin{4};
        L=varargin{5};
        W=varargin{6};
        outsav=obs;
        [out,varargout{1},varargout{2}]=selectmap(WX,variable,obs,x,y,'poly');  
        Iclick=find((outsav-out)~=0);
        if ~isempty(Iclick)
            for k=1:length(Iclick)
                Jvois=find(W(Iclick(k),:)~=0);
                L(Iclick(k),Jvois)=1-L(Iclick(k),Jvois);
                L(Jvois,Iclick(k))=1-L(Jvois,Iclick(k));
            end;
        end;
        varargout{3}=L;
    end;
case 'neighbour'

    switch lower(varargin{1})
     case 'mappoint'
        I=varargin{2};
        J=varargin{3};
        W=varargin{4};
        L=varargin{5};
        x=varargin{6};
        y=varargin{7};
        long=varargin{8};
        lat=varargin{9};
        Iclick=varargin{10};
        diff=abs(long-x)*(max(lat)-min(lat))+abs(lat-y)*(max(long)-min(long));
        i=find(diff==min(diff));
        if diff(i)/((max(long)-min(long))*(max(lat)-min(lat)))<0.01
            i=i(1);
            obs(i)=1;
            Jvois=find(W(i,:)~=0);
            obs(Jvois)=1;
            L(i,Jvois)=1;
            L=(L | L');
            Iclick(i)=1;
        end;
        out=obs;
        varargout{1}=L;
        varargout{2}=Iclick;
     case 'mappoly'
        I=varargin{2};
        J=varargin{3};
        W=varargin{4};
        L=varargin{5};
        x=varargin{6};
        y=varargin{7};
        long=varargin{8};
        lat=varargin{9};
        Iclick=varargin{10};
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
                L2=inpolygon(long,lat,vectx,vecty);
                L2=find(L2~=0);
                if ~isempty(L2)
                    obs(L2)=1;
                    for k=1:length(L2)
                        Jvois=find(W(L2(k),:)~=0);
                        obs(Jvois)=1;
                        L(L2(k),Jvois)=1;
                    end;
                    L=(L|L');
                    Iclick(L2)=1;
                end;
            end;
            p=p+1;
        end;
        varargout{1}=L;
        varargout{2}=Iclick;
        varargout{3}=vectx;
        varargout{4}=vecty;
        out=obs;
    otherwise   
        
        I=varargin{2};
        J=varargin{3};
        W=varargin{4};
        L=varargin{5};
        L2=varargin{6};
        x=varargin{7};
        y=varargin{8};
        varn1=variable(I);
        varn2=variable(J);
        diff=abs(varn1-x)*(max(variable)-min(variable))+abs(varn2-y)*(max(variable)-min(variable));
        i=find(diff==min(diff));
        i=i(1);
        if diff(i)/(((max(variable)-min(variable)))*(max(variable)-min(variable)))<0.01
            if L(I(i),J(i))==0 & (obs(I(i))==0 | obs(J(i))==0)
                obs(I(i))=1;
                obs(J(i))=1;
                L2(I(i),J(i))=1;
                if W(J(i),I(i))~=0
                    L2(J(i),I(i))=1;
                end;
                L(I(i),J(i))=1;
                L(J(i),I(i))=1;
            elseif L(I(i),J(i))==0
                L2(I(i),J(i))=1;
                if W(J(i),I(i))~=0
                    L2(J(i),I(i))=1;
                end;
                L(I(i),J(i))=1;
                L(J(i),I(i))=1;
            elseif L(I(i),J(i))==1
                Ipas0=find(L(I(i),:)~=0);
                Ipas0=Ipas0(find(Ipas0~=J(i)));
                Jpas0=find(L(J(i),:)~=0);
                Jpas0=Jpas0(find(Jpas0~=I(i)));
                L2(I(i),J(i))=0;
                if W(J(i),I(i))~=0
                    L2(J(i),I(i))=0;
                end;
                L(I(i),J(i))=0;
                L(J(i),I(i))=0;
                if isempty(Ipas0)
                    obs(I(i))=0;    
                end;
                if isempty(Jpas0)
                    obs(J(i))=0;
                end;
            end;
        end;
        varargout{1}=L;
        varargout{2}=L2;
        out=obs;
    end;
    
case 'scatter'
    switch lower(varargin{1})
    case 'class'
        var2=varargin{2};
        BUTTON=varargin{3};
        Hbutt=varargin{4};
        vectclass=varargin{5};
        affc=varargin{6};
        pushb=BUTTON-48;
        if pushb==0
            pushb=10;
        end;
        if pushb<=length(affc)
            set(Hbutt(pushb),'Value',1-get(Hbutt(pushb),'Value'));
            affc(pushb)=get(Hbutt(pushb),'Value');
            if ~isempty(vectclass{pushb}) & get(Hbutt(pushb),'Value')==1
                obs(vectclass{pushb})=1;         
            elseif ~isempty(vectclass{pushb}) & get(Hbutt(pushb),'Value')==0
                obs(vectclass{pushb})=0;        
            end;
        end;
        varargout{1}=affc;
        out=obs;
    case 'point'
        var2=varargin{2};
        x=varargin{3};
        y=varargin{4};
        [out,vectx,vecty]=selectmap(var2,variable,obs,x,y,'point');
    case 'poly'
        var2=varargin{2};
        x=varargin{3};
        y=varargin{4};
        [out,varargout{1},varargout{2}]=selectmap(var2,variable,obs,x,y,'poly');
    end;
case {'vario','angle'}
    switch lower(varargin{1})
    case 'point'
        H=varargin{2};
        V=varargin{3};
        Htri=varargin{4};
        Vtri=varargin{5};
        L=varargin{6};
        x=varargin{7};
        y=varargin{8};
        diff=abs(Htri-x)*(max(Vtri)-min(Vtri))+abs(Vtri-y)*(max(Htri)-min(Htri));
        i=find(diff==min(diff));
        if diff(i)/((max(Htri)-min(Htri))*(max(Vtri)-min(Vtri)))<0.01
            [I,J]=find(triu(H)==Htri(i) & triu(V)==Vtri(i));
            if L(I,J)==0 & (obs(I)==0 | obs(J)==0)
                obs(I)=1;
                obs(J)=1;
                L(I,J)=1;
                L(J,I)=1;
            elseif L(I,J)==0
                L(I,J)=1;
                L(J,I)=1;
            elseif L(I,J)==1
                Ipas0=find(L(I,:)~=0);
                Ipas0=Ipas0(find(Ipas0~=J));
                Jpas0=find(L(J,:)~=0);
                Jpas0=Jpas0(find(Jpas0~=I));
                L(I,J)=0;
                L(J,I)=0;
                if isempty(Ipas0)
                    obs(I)=0;    
                end;
                if isempty(Jpas0)
                    obs(J)=0;
                end;
            end;
        end;
        varargout{1}=L;
        out=obs;
    case 'poly'
        H=varargin{2};
        V=varargin{3};
        Htri=varargin{4};
        Vtri=varargin{5};
        L=varargin{6};
        x=varargin{7};
        y=varargin{8};
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
                L2=inpolygon(Htri,Vtri,vectx,vecty);
                L2=find(L2~=0);
                if ~isempty(L2)
                    for i=1:length(L2)
                        [I,J]=find(triu(H)==Htri(L2(i)) & triu(V)==Vtri(L2(i)));
                        if L(I,J)==0 & (obs(I)==0 | obs(J)==0)
                            obs(I)=1;
                            obs(J)=1;
                            L(I,J)=1;
                            L(J,I)=1;
                        elseif L(I,J)==0
                            L(I,J)=1;
                            L(J,I)=1;
                        elseif L(I,J)==1
                            Ipas0=find(L(I,:)~=0);
                            Ipas0=Ipas0(find(Ipas0~=J));
                            Jpas0=find(L(J,:)~=0);
                            Jpas0=Jpas0(find(Jpas0~=I));
                            L(I,J)=0;
                            L(J,I)=0;
                            if isempty(Ipas0)
                                obs(I)=0;    
                            end;
                            if isempty(Jpas0)
                                obs(J)=0;
                            end;
                         end;
                     end;
                 end;
            end;
            p=p+1;
        end;
        varargout{1}=L;
        varargout{2}=vectx;
        varargout{3}=vecty;
        out=obs;
    end;
   
case 'polybox'
    frtbasse=varargin{1};
    frthaute=varargin{2};
    q1=varargin{3};
    med=varargin{4};
    q3=varargin{5};
    vectbox=varargin{6};
    valeurs=varargin{7};
    var2=varargin{8};
    x=varargin{9};
    y=varargin{10};
    cote=[1:length(q1)];
    cote1=cote-0.25;
    cote2=cote+0.25;
    cote=sort([cote1,cote2]);
    X=sort([cote,x]);
    ib=find(X==x);
    if mod(ib,2)==0
        ib=ib/2;
        vb=vectbox{ib};
        if y>=frtbasse(ib) & y <q1(ib)
            I=find(vectbox{ib}>=frtbasse(ib) & vectbox{ib}<q1(ib));
        elseif y>=q1(ib) & y<med(ib)
            I=find(vectbox{ib}>=q1(ib) & vectbox{ib}<med(ib));
        elseif y>=med(ib) & y<q3(ib)
            I=find(vectbox{ib}>=med(ib) & vectbox{ib}<q3(ib));
        elseif y>=q3(ib) & y<frthaute(ib)
            I=find(vectbox{ib}>=q3(ib) & vectbox{ib}<=frthaute(ib));
        else
            diff=abs(vectbox{ib}-y);
            id=find(diff==min(diff));
            if (diff(id)/max(variable))<0.01
                I=id;
            else 
                I=[];
            end;
        end;
        if ~isempty(I)
            I1=[];
            for j=1:length(I)
                h=find(variable==vb(I(j)) & var2==valeurs(ib));
                I1=[I1;h];
            end;
            if obs(I1(1))==0;
                obs(I1)=1;
            else
                obs(I1)=0;
            end;
        end;
    end;
    out=obs;
case 'gini'
    FuncF=varargin{1};
    FuncG=varargin{2};
    Xk=varargin{3};
    x=varargin{4};
    matF=[Xk,FuncF];
    xsol=invgen(matF,x);
    i=find(Xk==xsol);
    G=FuncG(i);
    obs(find(variable<=xsol))=1;
    obs(find(variable>xsol))=0;
    out=obs;
    varargout{1}=G;
    varargout{2}=xsol;
case 'scatter3d' % proto
    var2=varargin{1};
    var3=varargin{2};
    cpa=varargin{3};
    cpa(:,1)=cpa(:,1)/(max(variable));
    cpa(:,2)=cpa(:,2)/max(var2);
    cpa(:,3)=cpa(:,3)/max(var3);
    direct=[cpa(1,1)-cpa(2,1);cpa(1,2)-cpa(2,2);cpa(1,3)-cpa(2,3)];
    variable=variable/(max(variable));
    var2=var2/max(var2);
    var3=var3/max(var3);
    direct=direct/norm(direct);
    vectcoord=[variable-repmat(cpa(2,1),length(variable),1),var2-repmat(cpa(2,2),length(var2),1),var3-repmat(cpa(2,3),length(var3),1)];
    normvect=sqrt(sum((vectcoord').*(vectcoord')));
    vectcoordn=vectcoord./repmat(normvect',1,3);
    coss=vectcoordn*direct;
    sins=sqrt(ones(length(var2),1)-coss.^2);
    dist=sins.*normvect';
    Iselect=find(dist==min(dist));
    if ~isempty(Iselect)
        if dist(Iselect)/max(dist)<0.02
            obs(Iselect)=1-obs(Iselect);
        end;
    end;
    out=obs;
end;